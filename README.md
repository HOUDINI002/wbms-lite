# WBMS-Lite

A small **Wi-Fi Billing and Management System**. A customer connects to the
hotspot, picks a package (for example 1 hour for 20 KES), pays by M-Pesa, and
is given internet access for the time they paid for. An admin manages packages,
vouchers and sessions.

WBMS-Lite is the sample project for the *WBMS Systems Course*. It is built one
small step at a time, with tests and a commit at every step. By default it runs
entirely on **mock adapters** (a fake payment gateway and a fake router), so you
need no M-Pesa account and no MikroTik router to develop or test it.

## Status

| Milestone | Scope | State |
|---|---|---|
| Lab 1 | Project skeleton, tooling, virtual environment | Done |
| M1 Foundation | Config, app factory, `/health`, database helper, schema, seed data | Done (Steps 1 to 3). Packages repository is next |
| M2 Catalog | Packages repository, service, admin CRUD, portal list | Not started |
| M3 Payments | Gateway interface, mock gateway, payment and callback flow | Not started |
| M4 Access | Sessions, router adapter, expiry worker | Not started |
| M5 Admin and vouchers | Login, dashboard, voucher CLI | Not started |

## Requirements

- **Python 3.12** (3.10 will fail with `cannot import name 'StrEnum'`)
- **Git**
- Windows PowerShell, or any macOS/Linux shell

## Quick start (Windows PowerShell)

```powershell
git clone https://github.com/HOUDINI002/wbms-lite.git
cd wbms-lite

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked, see Troubleshooting
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt

Copy-Item .env.example .env           # then edit .env, see Configuration
python -m pytest -v                   # everything should pass
```

## Quick start (macOS / Linux)

```bash
git clone https://github.com/HOUDINI002/wbms-lite.git
cd wbms-lite

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env                  # then edit .env, see Configuration
python -m pytest -v
```

**Pass test:** `python -m pytest -v` ends with all tests passing and the prompt
shows `(.venv)`.

## Configuration

Settings are read from environment variables. For local work put them in a
`.env` file in the project root. Real environment variables win over `.env`.
**Never commit `.env`**; only `.env.example` (with fake values) is tracked.

Create a proper secret key once and paste it into `.env`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

| Variable | Default | Required | Notes |
|---|---|---|---|
| `SECRET_KEY` | none | always | Signs sessions. The app refuses to start without it. |
| `DATABASE_PATH` | `instance/wbms.sqlite3` | no | SQLite file. Relative paths start at the project root; the folder is created on first use. Never commit it. |
| `PAYMENT_GATEWAY` | `mock` | no | `mock` or `daraja`. |
| `ROUTER_ADAPTER` | `mock` | no | `mock` or `mikrotik`. |
| `CALLBACK_SECRET` | empty | when `daraja` | Protects the payment callback URL. |
| `DARAJA_CONSUMER_KEY` | empty | when `daraja` | From the Safaricom developer portal. |
| `DARAJA_CONSUMER_SECRET` | empty | when `daraja` | From the Safaricom developer portal. |
| `DARAJA_SHORTCODE` | empty | when `daraja` | Business shortcode. |
| `DARAJA_PASSKEY` | empty | when `daraja` | Lipa na M-Pesa passkey. |
| `DARAJA_BASE_URL` | empty | when `daraja` | Sandbox or live API base URL. |
| `ADMIN_USERNAME` | `admin` | seed script only | Name of the first admin account. The web app itself never reads it. |
| `ADMIN_PASSWORD` | none | seed script only | Password for the first admin (10+ characters). Only its hash is stored. |

If a required value is missing the app stops at start-up with a `ConfigError`
that names every missing setting. Use the sandbox credentials while developing
and keep live credentials out of chat, screenshots and prompts.

## Daily commands

Run these from the project root with the virtual environment active.
Windows uses `tasks.ps1`; macOS/Linux use `make`. The task names are the same.

| Task | Windows | macOS / Linux | What it does |
|---|---|---|---|
| help | `.\tasks.ps1 help` | `make help` | List all tasks |
| venv | `.\tasks.ps1 venv` | `make venv` | Create `.venv` |
| install | `.\tasks.ps1 install` | `make install` | Install runtime and dev packages |
| run | `.\tasks.ps1 run` | `make run` | Start Flask in debug mode |
| test | `.\tasks.ps1 test` | `make test` | Run pytest |
| cov | `.\tasks.ps1 cov` | `make cov` | Tests with coverage, fails under 80 % |
| lint | `.\tasks.ps1 lint` | `make lint` | `ruff check` |
| format | `.\tasks.ps1 format` | `make format` | `ruff format` |
| initdb | `.\tasks.ps1 initdb` | `make initdb` | Create the database tables (no data) |
| clean | `.\tasks.ps1 clean` | `make clean` | Remove caches (keeps `.venv`) |

`make` is not installed on Windows by default; use `tasks.ps1` there. Always
type `python -m pytest -v` on **one line**.

To create the tables **and** the starter data (three example packages and one admin), set `ADMIN_PASSWORD` in `.env` and run:

```powershell
python scripts/seed.py
```

It is safe to run twice: nothing is duplicated and an existing admin's password is never changed.

Once the server is running, check it at <http://127.0.0.1:5000/health>. It
returns `{"status":"ok"}`.

## Project layout

```text
wbms-lite/
├── README.md, .env.example, Makefile, tasks.ps1
├── pyproject.toml, requirements.txt, requirements-dev.txt
├── Dockerfile, docker-compose.yml       placeholders for a later step
├── docs/                architecture, api, adr/
├── scripts/             scaffold.py, init_db.py (tables), seed.py (tables + starter data)
├── src/wbms/
│   ├── __init__.py      create_app(): the application factory, /health
│   ├── config.py        Settings and load_settings(): the only code reading the environment
│   ├── phone.py         phone-number normaliser (07..., 01..., +254... formats)
│   ├── db.py            get_db(), close_db(), transaction(), init_db()
│   ├── schema.sql       the six tables, constraints and indexes
│   ├── repositories/    the only code that contains SQL
│   ├── services/        business rules
│   ├── gateways/        payments/ and routers/ adapters (mock first)
│   ├── web/             routes, templates, static files
│   └── cli.py           voucher commands
└── tests/
    ├── conftest.py
    ├── unit/            fast tests, no network, no files outside tmp
    └── integration/     slower tests across layers
```

The layers, from the outside in: `web` translates HTTP to service calls,
`services` hold the business rules, `repositories` talk to SQLite, and
`gateways` talk to the outside world (M-Pesa, the router).

## Database access

All SQL runs on one SQLite connection per request, opened by `get_db()` and
closed automatically at the end of the request. Foreign keys are switched on for
every connection. Wrap multi-statement changes in a transaction so they succeed
or fail together:

```python
from wbms.db import transaction

with transaction() as db:
    db.execute("INSERT INTO customers (phone_number) VALUES (?)", (phone,))
    db.execute("UPDATE ...", (...))     # an exception here undoes both
```

Always pass values as `?` parameters, never by formatting them into the SQL.
Only the `repositories/` package should contain SQL.

## Data model

Defined in `src/wbms/schema.sql`. The database itself enforces the rules that
protect billing, so a bug in the code cannot silently corrupt money data.

| Table | Purpose | Rules worth knowing |
|---|---|---|
| `packages` | What can be bought: price, duration, speed, data limit | Price 0 or more, duration above 0, `NULL` data limit means unlimited, name is unique. Retire with `is_active = 0`, never delete |
| `customers` | One row per phone number, created on first payment | `phone_number` is unique |
| `transactions` | Every attempt to buy a package | Status is `pending`, `success` or `failed`. `gateway_ref` is unique. `paid_at` is set exactly when status is `success`. Method is `mpesa` or `voucher` |
| `sessions` | The internet access a paid transaction bought | `transaction_id` is unique, so a repeated payment callback can never create a second session. Expiry must be after start |
| `vouchers` | Prepaid codes | Code is unique. Status is `unused`, `redeemed` or `void`. `redeemed_at` is set exactly when redeemed |
| `admins` | Dashboard logins | Username is unique. Only a password hash is stored |

Conventions: money is whole KES in an `INTEGER`; every timestamp is UTC text
shaped like `2026-10-05T14:30:00Z`, which sorts correctly as plain text. Rows
that are still referenced cannot be deleted (`ON DELETE RESTRICT`).

## How we work

1. Branch from `main`: `git switch -c feature/short-description`.
2. Make one small change with its tests. Run `python -m pytest -v`.
3. Commit with a clear message, for example `feat(config): add Settings`.
   Prefixes in use: `feat`, `fix`, `docs`, `chore`, `build`, `test`.
4. Push the branch and open a pull request. Merge only when tests pass.
5. Tag each finished milestone (`m1-foundation`, `m2-catalog`, ...).

Your work lives on its feature branch until its pull request is merged on
GitHub. Run `git branch --show-current` before you start; if you switch to
`main` early, files such as `tasks.ps1` and `.gitignore` will seem to vanish.
When you merge a pull request on GitHub, choose **Create a merge commit**, not
*Squash*, so later branches built on top of it do not conflict.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Activate.ps1 cannot be loaded because running scripts is disabled` | PowerShell execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (this window only) |
| `cannot import name 'StrEnum' from 'enum'` | Running the global Python 3.10, not the venv | Activate `.venv` first; check `python --version` shows 3.12 |
| `make : The term 'make' is not recognized` | `make` is not on Windows | Use `.\tasks.ps1 <task>` |
| `ConfigError: SECRET_KEY is required` | No `.env`, or `SECRET_KEY` left blank. This is the app refusing to start on purpose. | `Copy-Item .env.example .env`, then set a real key (see Configuration) |
| `sqlite3.ProgrammingError: Cannot operate on a closed database` | A connection was kept after the request ended | Call `get_db()` inside the request or an app context; do not store the connection |
| pytest reports `rootdir: C:\Users\<you>` | Running from the wrong folder | `cd` into the project folder; `rootdir` must be the project root |
| `ModuleNotFoundError: No module named 'wbms'` when starting Flask by hand | `src/` is not on the import path | Use the `run` task, or set `PYTHONPATH=src` |
| `tasks.ps1` or `.gitignore` "disappeared" | You are on `main`, and the pull request is not merged yet | `git switch feature/<your-branch>` |
| `Cannot seed: ADMIN_PASSWORD is not set` | No admin password in `.env` | Add `ADMIN_PASSWORD=` followed by a password of 10+ characters, then run the script again |
| `SyntaxError` pointing at `<<<<<<<` in a `.py` file, or `needs merge` from Git | An unresolved merge conflict left markers in the file | Replace the file with a clean copy, then `git add <file>`. Find all markers with `Select-String -Path src\wbms\*.py -Pattern '^(<<<<<<<\|=======\|>>>>>>>)'` |
| `python -m` on one line and `pytest -v` on the next | Two separate commands | Type `python -m pytest -v` on a single line |
