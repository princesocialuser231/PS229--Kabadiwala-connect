# Kabadiwala Connect — SIH prototype

Local platform that lets a household book a priced scrap pickup, a collector manage the job, and ops see a digital earnings ledger.

## Run

```bash
python run.py
```

Open http://127.0.0.1:8000

- Household booking: `/`
- Track pickup: `/track.html`
- Collector desk: `/collector.html` (PIN `1234`)
- Ops desk: `/admin.html` (`ops` / `admin123`)

## Tests

```bash
python -m unittest tests.test_api
```

Uses Python 3 stdlib only (SQLite + `http.server`). No pip packages required.

## Demo path for judges

1. Filter Sector 12 and open Prince Kumar's rate list (newspaper is ₹15/kg, a collector-specific override).
2. Add 2 kg newspaper plus a custom item, submit a 10-digit phone.
3. Copy the `KC-` tracking code and open Track pickup.
4. Sign in as Prince Kumar, accept → en route → complete.
5. Confirm the earnings ledger row and the ops desk impact stats.
