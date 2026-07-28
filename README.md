# Hello Kids — School Management System

Manage children, teachers, classes, fee plans, receipts and attendance for a
**Hello Kids franchise preschool**.

Branding (logo, `#0054A5` blue / `#B3D648` lime palette, tagline and the
Pre-Nursery → UKG programme names) follows the franchise brand from
<https://www.hellokids.co.in>. Your branch's own name, address, phone and email
live in `backend/.env` and print on every fee receipt — **set them before you
issue receipts to parents**, since the defaults are placeholders.

To use different artwork, drop your file into `backend/app/assets/` and
`frontend/public/`, then point `SCHOOL_LOGO` at it in `backend/.env`.

- **Frontend** — React 19 + Vite + React Router (plain CSS, no UI framework)
- **Backend** — FastAPI (Python) with JWT auth
- **Database** — MongoDB (async driver, `pymongo.AsyncMongoClient`)
- **Receipts** — on-screen printable receipt **and** a downloadable A4 PDF (ReportLab)

---

## What it does

| Area | Features |
| --- | --- |
| **Children** | Enrolment with auto admission number, parents/guardian details, health & allergy notes, transport, photo-free profile cards, search + filters, per-child fee ledger |
| **Teachers** | Staff records with auto employee number, qualification, subjects, joining date, salary, payroll total, class assignment |
| **Classes** | Hello Kids programmes (Pre-Nursery/Play Group, Nursery/Montessori-1, LKG/Montessori-2, UKG/Montessori-3, Daycare, Activity Club) with room, capacity, class teacher and their **own fee structure** |
| **Fees** | Per-class fee components (one-time / monthly / quarterly / per-term / annual), **admin-negotiated agreed fee per child**, automatic instalment schedule with due dates, concessions spread proportionally over the year |
| **Dues tracking** | Total fee / paid / balance / next due on every row of the children list, a totals bar across the whole filter, and filters for *pending*, *overdue* and *fully paid* |
| **Payments** | Collect cash / UPI / card / cheque / bank transfer, auto-allocated to the earliest unpaid instalment, running balance, receipt cancellation with reason (admin only) |
| **Receipts** | Sequential receipt numbers (`RCP/2026-27/00001`), amount in words (Indian numbering), print view and PDF download |
| **Attendance** | Daily class roll call (present / absent / late / holiday), per-child attendance % over 30 days |
| **Reports** | Collection by month / mode / class, outstanding & overdue dues, CSV export |
| **Users** | Admin / staff / teacher roles, password change, account enable-disable |

---

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.11+ | 3.14 works (needs `pydantic>=2.12`, already pinned) |
| Node.js | 20+ | tested on 24 |
| MongoDB | 6.0+ | **not currently installed on this machine** — see below |

### Getting MongoDB

**A. MongoDB Atlas — free, nothing to install**

1. Create a free **M0** cluster at <https://www.mongodb.com/cloud/atlas>.
2. **Database Access** → add a database user, note the username and password.
3. **Network Access** → add your current IP to the IP Access List.
   (For a quick trial you can allow `0.0.0.0/0`, but don't leave that on.)
4. **Connect → Drivers → Python** → copy the connection string into
   `backend/.env`:

   ```env
   MONGODB_URI=mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   MONGODB_DB=preschool
   ```

   Replace `<password>` with the real password. **If it contains any of
   `@ : / ? # [ ] %`, URL-encode it** — e.g. `p@ss` becomes `p%40ss`. This is by
   far the most common Atlas setup mistake.

5. Confirm it works before starting the API:

   ```powershell
   cd backend
   .\.venv\Scripts\python.exe -m app.check_db
   ```

   It prints `CONNECTED` plus the collection counts, or an exact diagnosis
   (wrong password / IP not allow-listed / cluster paused / malformed URI).

**B. Or install MongoDB locally (Windows)**

```powershell
winget install MongoDB.Server
```

It runs as a Windows service on `mongodb://localhost:27017`, which is the
built-in default — no `.env` change needed.

> Free Atlas clusters pause after a period of inactivity. If the app suddenly
> can't connect, open the Atlas dashboard and resume the cluster.

---

## Setup

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env      # set MONGODB_URI and change JWT_SECRET
.\.venv\Scripts\python.exe -m app.check_db          # confirm the database is reachable
.\.venv\Scripts\python.exe -m app.init_db           # create collections, indexes and the admin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

`init_db` is optional — the API creates the same collections and indexes on
startup — but it lets you set the database up (and confirm it) without starting
the server. It is safe to re-run.

The API runs at <http://127.0.0.1:8000>, interactive docs at
<http://127.0.0.1:8000/docs>.

On the very first start the backend creates the admin account from `.env`
(`ADMIN_EMAIL` / `ADMIN_PASSWORD`, default `admin@school.com` / `admin123`).

**Optional — load realistic demo data** (4 classes, 5 teachers, ~25 children with
fee plans, receipts and two weeks of attendance):

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.seed          # add demo data
.\.venv\Scripts\python.exe -m app.seed --reset  # wipe everything first, then seed
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> and sign in. The Vite dev server proxies `/api` to
`http://127.0.0.1:8000`, so there are no CORS issues in development.

### Shortcut

From the project root, in two terminals:

```powershell
.\start-backend.ps1
.\start-frontend.ps1
```

---

## How the fee logic works

This is the part worth understanding before you change anything.

The short version: **the class sets the standard fee, the admin sets the agreed
fee, and the schedule follows the agreed fee.**

1. **A class owns a fee structure** — a list of components, each with an amount
   and a frequency:

   | Frequency | Charged | Instalment months (session starts April) |
   | --- | --- | --- |
   | `one_time` | 1× | April |
   | `annual` | 1× | April |
   | `term` | 3× | April, August, December |
   | `quarterly` | 4× | April, July, October, January |
   | `monthly` | 12× | every month |

   The amount is **per occurrence**, so "Tuition Fee ₹4,200 monthly" means
   ₹50,400 across the year.

2. **Selecting a class on the enrolment form loads that class's total** into the
   *Total fee agreed with parents* box, along with a breakdown of the
   components. The admin overrides it with whatever was actually settled in the
   discussion with the parents. The form shows the difference live as a
   concession (agreed below standard) or as an amount above standard.

3. **Enrolling snapshots the plan** onto the child, with a dated **instalment
   schedule** scaled to the agreed total. The concession is spread
   proportionally over the whole year rather than dumped on month one, and
   instalments are rounded to whole rupees with the final row absorbing the
   remainder — so `sum(instalments) == agreed fee` exactly, always.

   The plan keeps `gross` (the class standard) alongside `agreed_total`, so you
   can always see what was given away and why (`discount_reason`).

   A child can also be enrolled with **no class at all** — just type an agreed
   fee and it becomes a single instalment.

4. **The first instalment can be collected on the enrolment form itself** — tick
   *Collect the first instalment now*, enter the amount and mode, and submitting
   enrols the child **and** issues the receipt in one step. The app then opens
   that receipt, ready to print or download. Later payments go through
   **Collect Fee** or the **Collect payment** button on the child's profile.

5. **A payment** is applied to the earliest unpaid instalment first, and the
   receipt lines are generated from that allocation ("Apr 2026 - Admission Fee,
   Tuition Fee"). Anything beyond the total payable is recorded as
   "Advance / Other".

6. **Instalment status** is derived, never stored: `paid`, `partial`,
   `overdue` (past its due date with a balance) or `due`.

7. **Changing a class's fee structure does not retroactively change existing
   children** — their snapshot stays put. Use **Edit fee agreement** on a
   child's profile to re-negotiate. Payments already recorded are never touched;
   the balance is simply recomputed against the new total. The app refuses to
   set an agreed fee below what has already been paid.

### Where to see dues

| Question | Where |
| --- | --- |
| What does this one child owe? | Child profile → *Fees & receipts* — full instalment schedule with paid / balance / status per row |
| Who owes money right now? | **Children** list — total fee, paid, balance and next due on every row, with a *Has pending dues* / *Overdue only* filter, plus a totals bar for the whole filter |
| What is outstanding across the school? | **Collect Fee** page → *Outstanding dues* table, and **Reports** → outstanding + overdue with CSV export |
| What came in this month? | **Dashboard** and **Reports** → collection by month / mode / class |

---

## Project layout

```
student-management/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, CORS, startup, admin bootstrap
│   │   ├── config.py            settings from backend/.env
│   │   ├── db.py                Mongo connection + indexes
│   │   ├── deps.py              auth dependencies, role guards
│   │   ├── security.py          bcrypt hashing, JWT issue/verify
│   │   ├── schemas.py           all Pydantic request/response models
│   │   ├── utils.py             serialisation, date encoding, amount-in-words
│   │   ├── seed.py              demo data generator
│   │   ├── check_db.py          connection tester with setup diagnostics
│   │   ├── init_db.py           create collections, indexes and first admin
│   │   ├── routers/             auth, students, teachers, classrooms,
│   │   │                        fees, attendance, dashboard
│   │   └── services/
│   │       ├── counters.py      atomic admission / employee / receipt numbers
│   │       ├── fees.py          fee plan, instalments, allocation, ledger
│   │       ├── payments.py      receipt creation shared by enrolment + counter
│   │       └── receipt_pdf.py   A4 receipt PDF
│   ├── tests/                   runnable test scripts — see tests/README.md
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── pages/               Login, Dashboard, Students, StudentDetail,
    │   │                        Teachers, Classes, Fees, Receipts,
    │   │                        ReceiptView, Attendance, Reports, Users
    │   ├── components/          Layout, StudentForm, PaymentForm, Toast, ui
    │   ├── context/AuthContext.jsx
    │   └── lib/                 api.js (axios + JWT), format.js
    ├── vite.config.js           /api dev proxy
    └── package.json
```

---

## API reference (summary)

All routes except `/api/auth/login` need `Authorization: Bearer <token>`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/login` | sign in, returns JWT + user |
| GET | `/api/auth/me` | current user |
| POST | `/api/auth/change-password` | change own password |
| GET/POST/PATCH/DELETE | `/api/users` | user admin (admin only) |
| GET | `/api/dashboard` | headline stats, trends, recent activity |
| GET | `/api/settings` | school branding for headers and receipts |
| GET/POST/PATCH/DELETE | `/api/classrooms` | classes + fee structures |
| GET/POST/PATCH/DELETE | `/api/students` | children |
| POST | `/api/students/{id}/fee-plan` | (re)build the instalment schedule |
| GET/POST/PATCH/DELETE | `/api/teachers` | staff |
| GET | `/api/fees/ledger/{student_id}` | payable / paid / balance + schedule |
| POST | `/api/fees/payments` | collect a payment, issues the receipt |
| GET | `/api/fees/payments` | receipt list with filters + totals |
| POST | `/api/fees/payments/{id}/cancel` | cancel a receipt (admin only) |
| GET | `/api/fees/receipts/{id}` | receipt data for the print view |
| GET | `/api/fees/receipts/{id}/pdf` | A4 PDF receipt |
| GET | `/api/fees/dues` | outstanding / overdue report |
| GET | `/api/fees/summary` | collection by month, mode and class |
| GET/POST | `/api/attendance` | daily roll-call sheet / bulk save |
| GET | `/api/attendance/student/{id}` | a child's attendance history |

---

## Roles

| Capability | Admin | Staff | Teacher |
| --- | :---: | :---: | :---: |
| View everything | ✅ | ✅ | ✅ |
| Add/edit children, teachers, classes | ✅ | ✅ | — |
| Collect fees & issue receipts | ✅ | ✅ | — |
| Save attendance | ✅ | ✅ | ✅ |
| Delete records, cancel receipts | ✅ | — | — |
| Manage user accounts | ✅ | — | — |

---

## Deploying to Azure

The app deploys as **one** Azure App Service. The GitHub Actions workflow builds
the React app, copies it into `backend/static`, and FastAPI serves both the API
and the UI from the same origin — so there is one resource to pay for, one URL,
and no CORS to configure. MongoDB stays on Atlas.

```
GitHub push to main
   -> Actions: npm ci && npm run build
   -> copy frontend/dist  ->  backend/static
   -> zip-deploy backend/  ->  Azure App Service (Linux, Python 3.12)
                                    |
                                    +-- MongoDB Atlas (unchanged)
```

### 1. Create the App Service

In the [Azure Portal](https://portal.azure.com) → **Create a resource** → **Web App**:

| Setting | Value |
| --- | --- |
| Resource Group | `hellokids-rg` (create new) |
| Name | `hellokids-school-management` (must be globally unique) |
| Publish | **Code** |
| Runtime stack | **Python 3.12** |
| Operating System | **Linux** |
| Region | **Central India** (closest to Bengaluru) |
| Pricing plan | **B1 Basic** (~₹1,100/month) or **F1 Free** to trial |

> F1 Free is fine for testing but sleeps when idle and is capped at 60 CPU
> minutes/day — too tight for daily front-desk use. B1 is the realistic choice.

If you pick a different name, update `AZURE_WEBAPP_NAME` in
[.github/workflows/azure-deploy.yml](.github/workflows/azure-deploy.yml).

### 2. Configure the app settings

App Service → **Settings → Environment variables → App settings**. Add each of
these (these are your secrets — they live here, never in the repo):

| Name | Value |
| --- | --- |
| `MONGODB_URI` | your Atlas connection string |
| `MONGODB_DB` | `preschool` |
| `JWT_SECRET` | the long random value from your local `backend/.env` |
| `SCHOOL_NAME` | `Hello Kids Preschool` |
| `SCHOOL_BRANCH` | `Bells` |
| `SCHOOL_TAGLINE` | `The Power of Early Childhood Education` |
| `SCHOOL_ADDRESS` | your branch address |
| `SCHOOL_PHONE` | `7760022267` |
| `SCHOOL_EMAIL` | `hellokidsbells1@gmail.com` |
| `ACADEMIC_YEAR` | `2026-27` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | only used if the database has no users yet |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` — makes Azure run `pip install` |

Then **Settings → Configuration → General settings → Startup Command**:

```
gunicorn --bind=0.0.0.0:8000 --timeout 600 -k uvicorn.workers.UvicornWorker app.main:app
```

### 3. Let Atlas accept connections from Azure

Atlas → **Network Access**. App Service outbound IPs change, so either add the
App Service's outbound IP list (App Service → *Networking* → *Outbound
addresses*), or allow `0.0.0.0/0` and rely on the database username/password.
Nothing connects without the credentials, but the IP list is the tighter option.

### 4. Wire up the deployment

1. App Service → **Deployment Center** → *Manage publish profile* → **Download
   publish profile**.
2. GitHub repo → **Settings → Secrets and variables → Actions → New repository
   secret**, named `AZURE_WEBAPP_PUBLISH_PROFILE`, pasting the whole file.
3. Push to `main` (or run the workflow manually from the **Actions** tab).

The workflow builds, runs the offline test suite, and deploys. Your app is then
at `https://<app-name>.azurewebsites.net`.

### 5. First run

Visit the site and sign in. The API creates the admin account on first start if
the `users` collection is empty — but your Atlas database already has yours, so
sign in with your existing email and password.

### Troubleshooting

| Symptom | Cause |
| --- | --- |
| 500 on every page | `MONGODB_URI` missing or Atlas blocking the IP — check App Service → *Log stream* |
| UI loads but API 404s | Startup command not set, so Azure is running its default handler |
| "Application Error" | Build failed — set `SCM_DO_BUILD_DURING_DEPLOYMENT=true` |
| Login works locally, not on Azure | `JWT_SECRET` differs between the two; that is expected and fine |

---

## Before going live

1. Set a long random `JWT_SECRET` in `backend/.env`.
2. Change the default admin password (Users → Change my password).
3. **Set your branch details in `.env`** — `SCHOOL_BRANCH`, `SCHOOL_ADDRESS`,
   `SCHOOL_PHONE` and `SCHOOL_EMAIL` ship as `<< placeholder >>` text and are
   printed on every receipt a parent receives. Use your branch's contact
   details, not the franchise head office's.
4. Set `ACADEMIC_YEAR` and `SESSION_START_MONTH` for your session (default is
   April, the Indian academic year).
5. Restrict `CORS_ORIGINS` to your real frontend domain.
6. Build the frontend with `npm run build` and serve `frontend/dist` behind
   nginx/IIS, with `/api` reverse-proxied to uvicorn.
7. Turn on MongoDB authentication and schedule `mongodump` backups.
