"""API tests for the SIH prototype. Run: python -m unittest tests.test_api"""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from backend.server import make_server


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = TemporaryDirectory()
        db_path = Path(cls.tmp.name) / "test.db"
        cls.httpd = make_server(db_path, port=8765)
        cls.base = "http://127.0.0.1:8765"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        from backend import server as server_mod
        if server_mod.APP:
            server_mod.APP.close()
            server_mod.APP = None
        cls.tmp.cleanup()

    def request(self, method: str, path: str, body=None, token: str | None = None, expected=200):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as res:
                payload = json.loads(res.read().decode("utf-8"))
                self.assertEqual(res.status, expected)
                return payload
        except HTTPError as err:
            payload = json.loads(err.read().decode("utf-8"))
            if err.code != expected:
                self.fail(f"{method} {path} expected {expected} got {err.code}: {payload}")
            return payload

    def test_health(self):
        data = self.request("GET", "/api/health")
        self.assertTrue(data["ok"])

    def test_distance_sort(self):
        data = self.request("GET", "/api/kabadiwalas?lat=28.5921&lng=77.3345")
        self.assertIn("distance_km", data["kabadiwalas"][0])
        self.assertEqual(data["kabadiwalas"][0]["name"], "Prince Kumar")
        self.assertLessEqual(
            data["kabadiwalas"][0]["distance_km"],
            data["kabadiwalas"][-1]["distance_km"],
        )

    def test_kabadiwalas_and_area_filter(self):
        data = self.request("GET", "/api/kabadiwalas")
        self.assertGreaterEqual(len(data["kabadiwalas"]), 3)
        filtered = self.request("GET", "/api/kabadiwalas?q=Sector%2012")
        self.assertEqual(len(filtered["kabadiwalas"]), 1)
        self.assertEqual(filtered["kabadiwalas"][0]["name"], "Prince Kumar")

    def test_catalog_rate_override(self):
        data = self.request("GET", "/api/kabadiwalas/1/catalog")
        newspaper = next(i for i in data["items"] if i["name"] == "Newspaper")
        self.assertEqual(newspaper["rate_per_kg"], 15)

    def test_unknown_kabadiwala_catalog(self):
        self.request("GET", "/api/kabadiwalas/99/catalog", expected=404)

    def test_pickup_validation(self):
        self.request(
            "POST",
            "/api/pickups",
            {
                "kabadiwala_id": 1,
                "household_name": "Asha",
                "household_phone": "123",
                "address": "12 MG Road",
                "preferred_time": "2026-09-15T10:00",
                "items": [{"name": "Newspaper", "weight_kg": 2}],
            },
            expected=400,
        )

    def test_full_pickup_lifecycle_and_ledger(self):
        created = self.request(
            "POST",
            "/api/pickups",
            {
                "kabadiwala_id": 1,
                "household_name": "Asha Verma",
                "household_phone": "9876543210",
                "address": "12 MG Road, Sector 12",
                "preferred_time": "2026-09-15T10:00",
                "items": [
                    {"name": "Newspaper", "weight_kg": 2},
                    {"name": "Old mixer", "weight_kg": 3, "is_custom": True},
                ],
            },
            expected=201,
        )
        self.assertTrue(created["tracking_code"].startswith("KC-"))
        self.assertEqual(created["status"], "pending")
        self.assertEqual(created["estimated_total"], 30)

        tracked = self.request("GET", "/api/pickups/" + created["tracking_code"])
        self.assertEqual(len(tracked["items"]), 2)

        by_phone = self.request("GET", "/api/household/pickups?phone=9876543210")
        self.assertTrue(any(p["tracking_code"] == created["tracking_code"] for p in by_phone["pickups"]))

        login = self.request("POST", "/api/auth/collector", {"kabadiwala_id": 1, "pin": "1234"})
        token = login["token"]

        bad = self.request("POST", "/api/auth/collector", {"kabadiwala_id": 1, "pin": "0000"}, expected=401)
        self.assertIn("Invalid", bad["error"])

        accepted = self.request(
            "PATCH",
            f"/api/pickups/{created['id']}/status",
            {"status": "accepted"},
            token=token,
        )
        self.assertEqual(accepted["status"], "accepted")

        illegal = self.request(
            "PATCH",
            f"/api/pickups/{created['id']}/status",
            {"status": "completed"},
            token=token,
            expected=400,
        )
        self.assertIn("Cannot move", illegal["error"])

        self.request("PATCH", f"/api/pickups/{created['id']}/status", {"status": "en_route"}, token=token)
        completed = self.request(
            "PATCH",
            f"/api/pickups/{created['id']}/status",
            {"status": "completed"},
            token=token,
        )
        self.assertEqual(completed["status"], "completed")

        desk = self.request("GET", "/api/collector/pickups", token=token)
        self.assertEqual(len(desk["ledger"]), 1)
        self.assertEqual(desk["ledger"][0]["amount"], 30)

        other = self.request("POST", "/api/auth/collector", {"kabadiwala_id": 2, "pin": "1234"})
        self.request(
            "PATCH",
            f"/api/pickups/{created['id']}/status",
            {"status": "cancelled"},
            token=other["token"],
            expected=401,
        )

        admin = self.request("POST", "/api/auth/admin", {"username": "ops", "pin": "admin123"})
        ops = self.request("GET", "/api/admin/pickups", token=admin["token"])
        self.assertGreaterEqual(ops["stats"]["completed_count"], 1)
        self.assertGreaterEqual(ops["stats"]["kg_diverted"], 5)

    def test_static_home_is_served(self):
        with urlopen(self.base + "/", timeout=5) as res:
            html = res.read().decode("utf-8")
        self.assertIn("Kabadiwala Connect", html)
        self.assertIn("area-search", html)

    def test_backend_dir_is_blocked(self):
        req = Request(self.base + "/backend/server.py")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
