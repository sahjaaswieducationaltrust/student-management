# Tests

Plain scripts — no pytest needed. Run them from the `backend` folder with the
virtualenv's Python.

```powershell
cd backend
.\.venv\Scripts\python.exe tests\test_fee_logic.py   # offline, no database
.\.venv\Scripts\python.exe tests\test_e2e_core.py    # needs a database
.\.venv\Scripts\python.exe tests\test_e2e_fees.py    # needs a database
```

Each exits `0` on success and prints a per-check `OK` / `FAIL` line.

| File | Covers |
| --- | --- |
| `test_fee_logic.py` | Fee plan generation, instalment scheduling, concession spreading, payment allocation, amount-in-words, receipt PDF rendering, OpenAPI route registration. No database required. |
| `test_e2e_core.py` | Login, roles, classes, enrolment, payments, receipts + PDF, cancellation, attendance, dashboard, reports, validation guard rails. |
| `test_e2e_fees.py` | Negotiated fee agreement (below / above standard), first instalment collected at enrolment, dues filters and totals, re-negotiating a fee after payments exist. |

## Safety

The two end-to-end scripts set `MONGODB_DB=preschool_e2e_temp` before importing
the app, so they run against a **throwaway database on your configured cluster**
and drop it when they finish. Your real `preschool` data is never touched.

If a run crashes part-way the temp database can survive; the next run starts from
whatever was left, which shows up as doubled counts. Drop it manually if that
happens:

```powershell
.\.venv\Scripts\python.exe -c "import asyncio; from pymongo import AsyncMongoClient; from app.config import settings; asyncio.run(AsyncMongoClient(settings.mongodb_uri).drop_database('preschool_e2e_temp'))"
```

`test_e2e_core.py` also needs `httpx` (`pip install httpx`), which is not in
`requirements.txt` because the app itself does not need it.
