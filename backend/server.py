"""Stdlib HTTP API + static file server for the SIH prototype."""

from __future__ import annotations

import json
import math
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from backend.database import ROOT, connect, init_db

HOST = "127.0.0.1"
PORT = 8000
PHONE_RE = re.compile(r"^[6-9]\d{9}$")
VALID_STATUSES = ("pending", "accepted", "en_route", "completed", "cancelled")
TRANSITIONS = {
    "pending": {"accepted", "cancelled"},
    "accepted": {"en_route", "cancelled"},
    "en_route": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    if None in (lat1, lng1, lat2, lng2):
        return 999.0
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def digits_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")[-10:]


class App:
    def __init__(self, db_path: Path | None = None) -> None:
        self.conn = connect(db_path)
        init_db(self.conn)

    def close(self) -> None:
        self.conn.close()

    def catalog_for(self, kabadiwala_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT c.id, c.name, c.icon, c.category,
                   COALESCE(r.rate_per_kg, c.rate_per_kg) AS rate_per_kg
            FROM catalog_items c
            LEFT JOIN kabadiwala_rates r
              ON r.item_id = c.id AND r.kabadiwala_id = ?
            ORDER BY c.id
            """,
            (kabadiwala_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        totals = self.conn.execute(
            """
            SELECT
              COUNT(*) AS pickup_count,
              COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_count,
              COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
              COALESCE((
                SELECT SUM(weight_kg) FROM pickup_items pi
                JOIN pickups p ON p.id = pi.pickup_id
                WHERE p.status = 'completed'
              ), 0) AS kg_diverted,
              COALESCE((SELECT SUM(amount) FROM earnings_ledger), 0) AS collector_earnings
            FROM pickups
            """
        ).fetchone()
        return row_to_dict(totals) or {}

    def create_pickup(self, payload: dict[str, Any]) -> dict[str, Any]:
        kabadiwala_id = int(payload.get("kabadiwala_id") or 0)
        name = str(payload.get("household_name") or "").strip()
        phone = digits_phone(str(payload.get("household_phone") or ""))
        address = str(payload.get("address") or "").strip()
        preferred_time = str(payload.get("preferred_time") or "").strip()
        area = str(payload.get("area") or "").strip() or None
        items = payload.get("items") or []

        if not kabadiwala_id or not name or not address or not preferred_time:
            raise ValueError("Missing required pickup fields.")
        if not PHONE_RE.match(phone):
            raise ValueError("Enter a valid 10-digit Indian mobile number.")
        if not isinstance(items, list) or not items:
            raise ValueError("Cart cannot be empty.")

        kabadiwala = self.conn.execute(
            "SELECT * FROM kabadiwalas WHERE id = ?", (kabadiwala_id,)
        ).fetchone()
        if not kabadiwala:
            raise ValueError("Selected kabadiwala was not found.")

        rates = {row["name"]: row["rate_per_kg"] for row in self.catalog_for(kabadiwala_id)}
        clean_items = []
        estimated = 0.0
        for raw in items:
            item_name = str(raw.get("name") or "").strip()
            weight = float(raw.get("weight_kg") or 0)
            is_custom = bool(raw.get("is_custom"))
            if not item_name or weight <= 0 or weight > 500:
                raise ValueError("Each item needs a name and a weight between 0 and 500 kg.")
            rate = None if is_custom else rates.get(item_name)
            if not is_custom and rate is None:
                raise ValueError(f"Unknown catalog item: {item_name}")
            if rate is not None:
                estimated += rate * weight
            clean_items.append((item_name, weight, rate, 1 if is_custom else 0))

        tracking = "KC-" + secrets.token_hex(3).upper()
        now = utc_now()
        cur = self.conn.execute(
            """
            INSERT INTO pickups (
                tracking_code, kabadiwala_id, household_name, household_phone,
                address, area, preferred_time, status, estimated_total,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                tracking,
                kabadiwala_id,
                name,
                phone,
                address,
                area,
                preferred_time,
                round(estimated, 2),
                now,
                now,
            ),
        )
        pickup_id = cur.lastrowid
        self.conn.executemany(
            """INSERT INTO pickup_items (pickup_id, item_name, weight_kg, rate_per_kg, is_custom)
               VALUES (?, ?, ?, ?, ?)""",
            [(pickup_id, *item) for item in clean_items],
        )
        self.conn.commit()
        return self.pickup_detail(tracking)

    def pickup_detail(self, tracking_code: str) -> dict[str, Any]:
        pickup = self.conn.execute(
            """
            SELECT p.*, k.name AS kabadiwala_name, k.phone AS kabadiwala_phone, k.area AS kabadiwala_area
            FROM pickups p
            JOIN kabadiwalas k ON k.id = p.kabadiwala_id
            WHERE p.tracking_code = ?
            """,
            (tracking_code.upper(),),
        ).fetchone()
        if not pickup:
            raise KeyError("Pickup not found.")
        items = self.conn.execute(
            "SELECT item_name, weight_kg, rate_per_kg, is_custom FROM pickup_items WHERE pickup_id = ?",
            (pickup["id"],),
        ).fetchall()
        data = row_to_dict(pickup)
        data["items"] = [row_to_dict(i) for i in items]
        return data

    def pickups_by_phone(self, phone: str) -> list[dict[str, Any]]:
        cleaned = digits_phone(phone)
        rows = self.conn.execute(
            """
            SELECT p.tracking_code, p.status, p.estimated_total, p.preferred_time,
                   p.created_at, k.name AS kabadiwala_name
            FROM pickups p
            JOIN kabadiwalas k ON k.id = p.kabadiwala_id
            WHERE p.household_phone = ?
            ORDER BY p.id DESC
            """,
            (cleaned,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]

    def login(self, subject_type: str, identifier: str, pin: str) -> dict[str, Any]:
        if subject_type == "collector":
            try:
                kid = int(identifier)
            except (TypeError, ValueError):
                raise PermissionError("Invalid collector login.")
            row = self.conn.execute(
                "SELECT id, name, pin FROM kabadiwalas WHERE id = ?",
                (kid,),
            ).fetchone()
            if not row or row["pin"] != pin:
                raise PermissionError("Invalid collector login.")
            subject_id = row["id"]
            name = row["name"]
        elif subject_type == "admin":
            row = self.conn.execute(
                "SELECT id, username, pin, role FROM staff WHERE username = ?",
                (identifier,),
            ).fetchone()
            if not row or row["pin"] != pin:
                raise PermissionError("Invalid ops login.")
            subject_id = row["id"]
            name = row["username"]
        else:
            raise ValueError("Unknown login type.")

        token = secrets.token_urlsafe(24)
        self.conn.execute(
            "INSERT INTO sessions (token, subject_type, subject_id, created_at) VALUES (?, ?, ?, ?)",
            (token, subject_type, subject_id, utc_now()),
        )
        self.conn.commit()
        return {"token": token, "subject_type": subject_type, "subject_id": subject_id, "name": name}

    def session(self, token: str | None) -> sqlite3.Row:
        if not token:
            raise PermissionError("Login required.")
        row = self.conn.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
        if not row:
            raise PermissionError("Session expired. Please log in again.")
        return row

    def collector_pickups(self, kabadiwala_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT p.*, (
                SELECT GROUP_CONCAT(item_name || ' ' || weight_kg || 'kg', ', ')
                FROM pickup_items WHERE pickup_id = p.id
            ) AS items_summary
            FROM pickups p
            WHERE p.kabadiwala_id = ?
            ORDER BY p.id DESC
            """,
            (kabadiwala_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]

    def admin_pickups(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT p.*, k.name AS kabadiwala_name
            FROM pickups p
            JOIN kabadiwalas k ON k.id = p.kabadiwala_id
            ORDER BY p.id DESC
            """
        ).fetchall()
        return [row_to_dict(r) for r in rows]

    def ledger(self, kabadiwala_id: int | None = None) -> list[dict[str, Any]]:
        if kabadiwala_id:
            rows = self.conn.execute(
                """
                SELECT e.*, k.name AS kabadiwala_name, p.tracking_code
                FROM earnings_ledger e
                JOIN kabadiwalas k ON k.id = e.kabadiwala_id
                LEFT JOIN pickups p ON p.id = e.pickup_id
                WHERE e.kabadiwala_id = ?
                ORDER BY e.id DESC
                """,
                (kabadiwala_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT e.*, k.name AS kabadiwala_name, p.tracking_code
                FROM earnings_ledger e
                JOIN kabadiwalas k ON k.id = e.kabadiwala_id
                LEFT JOIN pickups p ON p.id = e.pickup_id
                ORDER BY e.id DESC
                """
            ).fetchall()
        return [row_to_dict(r) for r in rows]

    def update_status(self, pickup_id: int, new_status: str, actor: sqlite3.Row) -> dict[str, Any]:
        if new_status not in VALID_STATUSES:
            raise ValueError("Invalid status.")
        pickup = self.conn.execute("SELECT * FROM pickups WHERE id = ?", (pickup_id,)).fetchone()
        if not pickup:
            raise KeyError("Pickup not found.")
        if actor["subject_type"] == "collector" and actor["subject_id"] != pickup["kabadiwala_id"]:
            raise PermissionError("This pickup is assigned to another kabadiwala.")
        allowed = TRANSITIONS[pickup["status"]]
        if new_status not in allowed:
            raise ValueError(f"Cannot move from {pickup['status']} to {new_status}.")

        now = utc_now()
        payout = pickup["actual_payout"]
        if new_status == "completed":
            payout = pickup["estimated_total"]
            existing = self.conn.execute(
                "SELECT id FROM earnings_ledger WHERE pickup_id = ?", (pickup_id,)
            ).fetchone()
            if not existing:
                self.conn.execute(
                    """INSERT INTO earnings_ledger (kabadiwala_id, pickup_id, amount, note, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        pickup["kabadiwala_id"],
                        pickup_id,
                        payout,
                        "Completed pickup payout (estimated)",
                        now,
                    ),
                )
        self.conn.execute(
            "UPDATE pickups SET status = ?, actual_payout = ?, updated_at = ? WHERE id = ?",
            (new_status, payout, now, pickup_id),
        )
        self.conn.commit()
        code = self.conn.execute(
            "SELECT tracking_code FROM pickups WHERE id = ?", (pickup_id,)
        ).fetchone()["tracking_code"]
        return self.pickup_detail(code)


APP: App | None = None


def get_app() -> App:
    if APP is None:
        raise RuntimeError("App is not initialized.")
    return APP


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _json(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > 100_000:
            raise ValueError("Request body too large.")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON object required.")
        return data

    def _token(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        if header.lower().startswith("bearer "):
            return header.split(" ", 1)[1].strip()
        return self.headers.get("X-Auth-Token")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api("GET", parsed)
            return
        blocked = ("/data", "/backend", "/tests", "/.git")
        if any(parsed.path == p or parsed.path.startswith(p + "/") for p in blocked):
            self.send_error(403, "Forbidden")
            return
        if parsed.path in ("/", ""):
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_api("POST", urlparse(self.path))

    def do_PATCH(self) -> None:  # noqa: N802
        self._handle_api("PATCH", urlparse(self.path))

    def _handle_api(self, method: str, parsed) -> None:
        app = get_app()
        path = parsed.path.rstrip("/") or "/"
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        try:
            result, code = self._route(app, method, path, query)
            self._json(code, result)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except PermissionError as exc:
            self._json(401, {"error": str(exc)})
        except KeyError as exc:
            self._json(404, {"error": str(exc)})
        except json.JSONDecodeError:
            self._json(400, {"error": "Invalid JSON."})
        except Exception:
            import traceback
            traceback.print_exc()
            self._json(500, {"error": "Unexpected server error."})

    def _route(self, app: App, method: str, path: str, query: dict[str, str]):
        if method == "GET" and path == "/api/health":
            return {"ok": True, "service": "kabadiwala-connect"}, 200

        if method == "GET" and path == "/api/stats":
            return app.stats(), 200

        if method == "GET" and path == "/api/kabadiwalas":
            q = (query.get("q") or "").strip().lower()
            rows = app.conn.execute(
                "SELECT id, name, area, phone, rating, verified, lat, lng FROM kabadiwalas ORDER BY rating DESC"
            ).fetchall()
            user_lat = query.get("lat")
            user_lng = query.get("lng")
            try:
                lat_f = float(user_lat) if user_lat else None
                lng_f = float(user_lng) if user_lng else None
            except ValueError:
                raise ValueError("lat and lng must be numbers.")
            data = []
            for r in rows:
                item = row_to_dict(r)
                if lat_f is not None and lng_f is not None:
                    item["distance_km"] = round(
                        _haversine(lat_f, lng_f, item["lat"], item["lng"]),
                        1,
                    )
                data.append(item)
            if q:
                data = [k for k in data if q in k["name"].lower() or q in k["area"].lower()]
            if lat_f is not None and lng_f is not None:
                data.sort(key=lambda k: k.get("distance_km") if k.get("distance_km") is not None else 999)
            return {"kabadiwalas": data}, 200

        m = re.fullmatch(r"/api/kabadiwalas/(\d+)/catalog", path)
        if method == "GET" and m:
            kid = int(m.group(1))
            exists = app.conn.execute("SELECT id FROM kabadiwalas WHERE id = ?", (kid,)).fetchone()
            if not exists:
                raise KeyError("Kabadiwala not found.")
            return {"items": app.catalog_for(kid)}, 200

        m = re.fullmatch(r"/api/pickups/([A-Za-z0-9-]+)", path)
        if method == "GET" and m:
            return app.pickup_detail(m.group(1)), 200

        if method == "GET" and path == "/api/household/pickups":
            phone = query.get("phone") or ""
            if not digits_phone(phone):
                raise ValueError("Phone is required.")
            return {"pickups": app.pickups_by_phone(phone)}, 200

        if method == "POST" and path == "/api/pickups":
            return app.create_pickup(self._read_json()), 201

        if method == "POST" and path == "/api/auth/collector":
            body = self._read_json()
            return app.login("collector", str(body.get("kabadiwala_id") or ""), str(body.get("pin") or "")), 200

        if method == "POST" and path == "/api/auth/admin":
            body = self._read_json()
            return app.login("admin", str(body.get("username") or ""), str(body.get("pin") or "")), 200

        if method == "GET" and path == "/api/collector/pickups":
            session = app.session(self._token())
            if session["subject_type"] != "collector":
                raise PermissionError("Collector login required.")
            return {
                "pickups": app.collector_pickups(session["subject_id"]),
                "ledger": app.ledger(session["subject_id"]),
            }, 200

        if method == "GET" and path == "/api/admin/pickups":
            session = app.session(self._token())
            if session["subject_type"] != "admin":
                raise PermissionError("Ops login required.")
            return {"pickups": app.admin_pickups(), "stats": app.stats(), "ledger": app.ledger()}, 200

        m = re.fullmatch(r"/api/pickups/(\d+)/status", path)
        if method == "PATCH" and m:
            session = app.session(self._token())
            if session["subject_type"] not in {"collector", "admin"}:
                raise PermissionError("Not allowed.")
            body = self._read_json()
            return app.update_status(int(m.group(1)), str(body.get("status") or ""), session), 200

        raise KeyError("Unknown API route.")


def make_server(db_path: Path | None = None, port: int = PORT) -> ThreadingHTTPServer:
    global APP
    APP = App(db_path)
    return ThreadingHTTPServer((HOST, port), Handler)


def main() -> None:
    httpd = make_server()
    print(f"Kabadiwala Connect prototype running at http://{HOST}:{PORT}")
    print("Household:  /")
    print("Track:      /track.html")
    print("Collector:  /collector.html  (PIN 1234)")
    print("Ops desk:   /admin.html      (ops / admin123)")
    httpd.serve_forever()
