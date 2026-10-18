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
| M1 Foundation | Config, app factory, `/health`, database helper, schema, seed data | Done (Steps 1 to 3) |
| M2 Catalog | Packages repository, service, admin CRUD, portal list | Done (Steps 4 to 6): repository, service and JSON API (admin login still a stub), and the captive portal page |
| M3 Payments | Gateway interface, mock gateway, payment and callback flow | Not started. Step 7 (payment interface and mock gateway) is next |
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

Run pytest, Git and the app from a **normal** PowerShell window, never an
"Administrator" one. A run as Administrator can leave folders (pytest's temp
folder, `.pytest_cache`) that a normal window may not touch afterwards; see
Troubleshooting.

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
├── scripts/             scaffold.py, init_db.py (tables), seed.py (tables + starter data),
│                        register_blueprints.py (wires the web blueprints into create_app)
├── src/wbms/
│   ├── __init__.py      create_app(): the application factory, /health
│   ├── config.py        Settings and load_settings(): the only code reading the environment
│   ├── phone.py         phone-number normaliser (07..., 01..., +254... formats)
│   ├── db.py            get_db(), close_db(), transaction(), init_db()
│   ├── schema.sql       the six tables, constraints and indexes
│   ├── repositories/    the only code that contains SQL (packages.py done)
│   ├── services/        business rules (packages.py done)
│   ├── gateways/        payments/ and routers/ adapters (mock first)
│   ├── web/             routes, templates, static files (api_packages.py, portal.py,
│   │                    templates/portal.html, static/portal.js and portal.css done)
│   └── cli.py           voucher commands
└── tests/
    ├── conftest.py
    ├── unit/            fast tests, no network, no files outside tmp
    ├── integration/     slower tests across layers
    └── js/              optional Node tests for portal.js (node --test tests/js/portal.test.js)
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

## Repositories

A repository hides the database behind methods named in business language, so
the code above it deals with plain objects and never with SQL or rows.
`src/wbms/repositories/packages.py` is the first one:

```python
from wbms.db import get_db
from wbms.repositories.packages import PackageInput, PackageRepository

repo = PackageRepository(get_db())          # needs an app context
repo.list_active()                          # list[Package], cheapest first
repo.get(1)                                 # Package or None (also finds retired ones)
new = repo.create(PackageInput(name="2 Hours", price_kes=35,
                               duration_minutes=120, speed_kbps=4000))
repo.update(new.id, PackageInput(name="2 Hours", price_kes=40,
                                 duration_minutes=120, speed_kbps=4000))
repo.set_active(new.id, False)              # retire it; never delete
```

Rules every repository follows:

- Values go in as `?` parameters. A search for an f-string containing SQL must
  find nothing (a test checks this).
- Rows become dataclasses in one private method, `_to_package`.
- A repository never commits. Wrap several changes in `wbms.db.transaction()`.
- Database rule violations (duplicate name, negative price) surface as
  `sqlite3.IntegrityError`. Friendly messages come from the service in Step 5.
- `set_active` on an unknown id raises `PackageNotFoundError`; `get` and
  `update` return `None` instead.

## Services

A service holds the business rules. It takes plain data in, calls repositories,
and raises errors a person can understand. It contains no SQL and never commits.
`src/wbms/services/packages.py` is the first one:

```python
from wbms.db import get_db, transaction
from wbms.repositories.packages import PackageRepository
from wbms.services.packages import PackageService, ValidationError

service = PackageService(PackageRepository(get_db()))
service.list_for_portal()                  # active packages, cheapest first
with transaction():                        # the caller owns the transaction
    try:
        service.create({"name": "2 Hours", "price_kes": 35,
                        "duration_minutes": 120, "speed_kbps": 4000})
    except ValidationError as error:
        print(error.errors)                # {"price_kes": "Must be a whole number from 0 to 100000."}
```

Package rules (slide 64):

| Field | Rule |
|---|---|
| `name` | 2 to 60 characters after trimming spaces; must be unique |
| `price_kes` | whole number, 0 to 100000 |
| `duration_minutes` | whole number, 1 to 43200 |
| `speed_kbps` | whole number, 64 to 100000 |
| `data_limit_mb` | positive whole number, or `null`/missing for unlimited |

- `ValidationError.errors` maps each broken field to a message, and **all**
  problems are reported at once. A body that is not an object is reported under
  the name `body`.
- Text such as `"20"`, decimals such as `20.5` or `20.0`, and `true`/`false` are
  refused for number fields.
- `is_active` is ignored on create and update. A package is retired through the
  repository's `set_active`, never through this service.
- A duplicate name becomes `{"name": "A package with this name already exists."}`.
- `update` raises `UnknownPackageError` for an unknown id. Input is validated
  first, so bad data for an unknown id reports the validation problems.
- `ValidationError` lives in `services/packages.py` for now. When another
  service needs it (Step 8, payments), move it to a shared module.

## Package API

JSON routes in `src/wbms/web/api_packages.py`. The blueprint must be registered
inside `create_app` in `src/wbms/__init__.py`, just before `return app`. The
easy way is the script, which also registers the portal blueprint and is safe to
run twice:

```powershell
python scripts/register_blueprints.py
```

By hand, the lines are:

```python
from wbms.web.api_packages import bp as api_packages_bp

app.register_blueprint(api_packages_bp)
```

| Method and path | Who | Success | Notes |
|---|---|---|---|
| `GET /api/packages` | public | `200 {"packages": [...]}` | Active packages only, cheapest first |
| `POST /api/packages` | admin | `201 {"package": {...}}` | Body is a JSON object with the fields above |
| `PUT /api/packages/<id>` | admin | `200 {"package": {...}}` | Replaces every editable field |

Every error has the same shape (`fields` appears only for validation errors):

```json
{"error": {"code": "validation_error", "message": "Some fields are not valid.",
           "fields": {"name": "Must be 2 to 60 characters."}}}
```

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | A rule is broken, the body is not a JSON object, or the name is taken |
| 404 | `not_found` | Unknown package id, or an unknown URL under `/api/` |
| 405 | `method_not_allowed` | Wrong method under `/api/` |

**Security:** `require_admin` is a stub until M5. Today **anyone who can reach
the server can create and change packages.** Run the app only on your own
computer (`127.0.0.1`) and never expose it to a network yet.

Try it with the server running (`.\tasks.ps1 run`) from a second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/packages

$body = @{ name = "3 Hours"; price_kes = 45; duration_minutes = 180; speed_kbps = 5000 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/packages -ContentType "application/json" -Body $body

# To read the body of a 400 or 404 instead of just "Bad Request":
try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/api/packages -ContentType "application/json" -Body '{"name":"x"}' }
catch { $_.ErrorDetails.Message }
```

Test packages made this way stay in your local database. Start clean any time
with `Remove-Item instance\wbms.sqlite3` and `python scripts/seed.py`.

## Captive portal

The customer-facing page: pick a package, enter a phone number, pay. Files:

| File | Role |
|---|---|
| `src/wbms/web/portal.py` | Blueprint with `GET /portal`; checks the MAC address and sets security headers |
| `src/wbms/web/templates/portal.html` | Jinja2 page, mobile first, no inline scripts or styles |
| `src/wbms/web/static/portal.js` | Vanilla JavaScript: loads packages, validates the phone number, posts the payment |
| `src/wbms/web/static/portal.css` | Light CSS, no framework |

Register it (together with the package API) with `python scripts/register_blueprints.py`,
or add `from wbms.web.portal import bp as portal_bp` and `app.register_blueprint(portal_bp)`
to `create_app`, before `return app`.

**How a captive portal works.** The router intercepts the first web request of a
device that has not paid and redirects it to our page, passing the device's MAC
address in the address, like this:

```text
http://<server>/portal?mac=AA:BB:CC:DD:EE:FF
```

Until the real router adapter (Step 13) we simulate the redirect by typing that
address in a browser. In Step 13 the MikroTik hotspot login page will be set to
redirect to this same `/portal` URL, filling in the device's MAC address. Open
the page without `?mac=` and it explains this and keeps **Pay** switched off.

Try it (server running with `.\tasks.ps1 run`, three packages seeded with
`python scripts/seed.py`). In Chrome or Edge press F12, then the phone icon
(Toggle device toolbar), and choose a phone size:

```text
http://127.0.0.1:5000/portal?mac=AA:BB:CC:DD:EE:FF
```

What the page does:

- Loads `GET /api/packages` and shows one card per package (name, price in KES,
  duration, speed, data limit). Text is inserted as plain text, never as markup.
- Checks the phone number in the browser: `07xx`, `01xx`, `2547xx` or `+2547xx`,
  with or without spaces. This is only a convenience; the server validates again.
- Sends `POST /api/payments` with JSON `{"package_id": 2, "phone": "+254712345678", "mac": "AA:BB:CC:DD:EE:FF"}`,
  with the button disabled while the request is pending.
- Shows errors in text under the field they belong to and in a status area read
  out by screen readers.

`POST /api/payments` does not exist until Step 8, so today **Pay** ends with
"Payments are not available right now". That is expected. The portal already
understands the answers Step 8 will give:

| Answer | What the customer sees |
|---|---|
| `2xx` | Check your phone and enter your M-Pesa PIN |
| `400` with `error.fields.phone` or `error.fields.package_id` | That message under the matching field |
| `429` | Too many attempts, wait a minute |
| `404`, `5xx` | Payments are not available or not responding, try again |
| No connection | Could not reach the server |

Security notes: an invalid MAC in the address is dropped, never echoed. The page
is sent with `Cache-Control: no-store`, `Referrer-Policy: no-referrer` and a
strict `Content-Security-Policy` (own files only, no inline code) because the
address contains a device identifier.

Tests: `python -m pytest -v` covers the blueprint and page. The phone and display
helpers in `portal.js` have optional tests that need Node 18 or newer:
`node --test tests/js/portal.test.js`.

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
| `.\tasks.ps1 : The term '.\tasks.ps1' is not recognized`, or `Activate.ps1` not found | You are in a sub-folder such as `scripts\` or `src\` | `cd $HOME\Documents\wbms-lite` first. `ls` must show `tasks.ps1` |
| `GET : The term 'GET' is not recognized` | `GET /health` is HTTP, not a PowerShell command | Open <http://127.0.0.1:5000/health> in a browser, or run `curl http://127.0.0.1:5000/health` in a second window |
| `Program 'code.cmd' failed to run: Access is denied` | The VS Code command-line launcher is blocked | Open VS Code from the Start menu, then File > Open Folder. Use `notepad .env` for a quick edit |
| `running scripts is disabled` every time you open PowerShell | `-Scope Process` forgets the setting when the window closes | Once: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| `ADMIN_PASSWORD` appears twice in `.env` | `.env.example` lines were appended to an existing `.env` | `(Select-String '^ADMIN_PASSWORD=' .env).Count` should print 1. Remove the placeholder line in Notepad. Never print the line itself: terminal history is saved |
| `warning: LF will be replaced by CRLF` | Git normalising line endings on Windows | Harmless. Ignore it |
| Many tests `ERROR at setup` with `PermissionError: [WinError 5] Access is denied: '...\Temp\pytest-of-<you>'`, plus `PytestCacheWarning ... .pytest_cache ... Permission denied` | An earlier pytest run in an **Administrator** window left folders your normal window cannot write to | Close any Administrator window. Delete the two folders (see the commands below this table), then run pytest from a normal window |
| `E402 Module level import not at top of file` from `.\tasks.ps1 lint` | An `import` line sits below other code | Move the import to the top of the file, or for one deliberate case add `  # noqa: E402` to that line |
| `Invoke-RestMethod : ... (400) Bad Request` and nothing else | PowerShell hides the response body | Wrap the call in `try { ... } catch { $_.ErrorDetails.Message }` (see Package API) |
| `GET /api/packages` returns an HTML 404, or `test_blueprint_is_registered_in_the_real_app` fails | The blueprint is not registered | Add the two lines from the Package API section to `create_app`, before `return app` |
| `No module named pytest` and the path shows `...\Python310\python.exe` | The virtual environment is not active, so the global Python ran | `.\.venv\Scripts\Activate.ps1`; the prompt must start with `(.venv)` |
| `.\tasks.ps1 lint` reports E402 (or other errors) in files under `.pytest_tmp\` | `--basetemp=.pytest_tmp` left copies of project files, and the folder was not ignored | `.pytest_tmp/` is in `.gitignore` from Step 6, and ruff skips ignored files. Delete the folder as well: `Remove-Item -Recurse -Force .pytest_tmp` |
| `git status` lists `.pytest_tmp/` files | They were committed before the ignore rule existed | `git rm -r --cached .pytest_tmp`, then commit |
| `GET /portal` returns 404, or `test_portal_is_registered_in_the_real_app` fails | The portal blueprint is not registered | `python scripts/register_blueprints.py` |
| The portal says "This page must be opened from the hotspot" and **Pay** is off | The address has no valid `mac` | Add `?mac=AA:BB:CC:DD:EE:FF` to the address |
| The portal says "We could not load the packages" | The server is not running, or the database has no packages | Start it with `.\tasks.ps1 run`, and run `python scripts/seed.py` once |
| **Pay** ends with "Payments are not available right now" | `POST /api/payments` is built in Step 8 | Expected until then |
| `node --test tests/js` fails with `MODULE_NOT_FOUND` | Node 21 and newer read a folder name as a pattern | Name the file: `node --test tests/js/portal.test.js` |

Clearing the pytest folders left behind by an Administrator run, from a normal
window in the project root:

```powershell
Remove-Item -Recurse -Force "$env:TEMP\pytest-of-$env:USERNAME", .pytest_cache
```

If that says *Access is denied*, open PowerShell **as Administrator once** and
run the next lines (replace `geek` with your Windows user name), then close that
window and go back to the normal one:

```powershell
takeown /F "C:\Users\geek\AppData\Local\Temp\pytest-of-geek" /R /D Y
icacls "C:\Users\geek\AppData\Local\Temp\pytest-of-geek" /grant "geek:(OI)(CI)F" /T
Remove-Item -Recurse -Force "C:\Users\geek\AppData\Local\Temp\pytest-of-geek"
takeown /F "C:\Users\geek\Documents\wbms-lite\.pytest_cache" /R /D Y
icacls "C:\Users\geek\Documents\wbms-lite\.pytest_cache" /grant "geek:(OI)(CI)F" /T
Remove-Item -Recurse -Force "C:\Users\geek\Documents\wbms-lite\.pytest_cache"
```

No Administrator access? Keep pytest out of the broken folders instead:
`python -m pytest -v -p no:cacheprovider --basetemp=.pytest_tmp`. The
`.pytest_tmp/` folder is already listed in `.gitignore`.

<!-- wbms:step-07 -->
## Payments: gateway interface and mock (Step 7)

`src/wbms/gateways/payments/` holds the `PaymentGateway` protocol, the
deterministic `MockPaymentGateway` (phone ending in 0 fails, ending in 9 stays
pending, anything else succeeds) and `get_gateway(settings)`.
Set `PAYMENT_GATEWAY=mock` (default) for development.

<!-- wbms:step-08 -->
## Payments: starting a payment (Step 8)

`POST /api/payments` with `{"phone": "0712345671", "package_id": 1, "mac": "AA:BB:CC:DD:EE:FF"}`

| Status | Meaning |
|---|---|
| 202 | `{"transaction_id": 12, "status": "pending"}` |
| 400 | invalid JSON, missing or invalid fields (`fields` lists them) |
| 429 | more than 5 requests per minute from one IP (see `Retry-After`) |
| 502 | payment provider failed; the transaction is marked `failed` |

A repeated request for the same phone and package within 2 minutes returns the
existing pending transaction instead of charging twice.

Existing databases need one migration (new `transactions.mac_address` column):

```powershell
python scripts\add_mac_to_transactions.py
```

| Step | Status |
|---|---|
| 1-6 Foundation, catalog, portal | done |
| 7 Payment interface and mock | done |
| 8 Start payment | done |
| 9 Payment callback | next |
Add-Content README.md (Get-Content docs\readme-step9-snippet.md -Raw)

<!-- wbms:step-09 -->
## Payments: the callback (Step 9)

`POST /api/payments/callback/<CALLBACK_SECRET>` receives the gateway result
(Daraja-style STK callback).

| Case | Result |
|---|---|
| wrong secret | 403, nothing changes |
| success, amount matches | transaction `success` with receipt and `paid_at`, session started |
| failure (for example ResultCode 1032) | transaction `failed` |
| duplicate, unknown reference, malformed body | 200, nothing changes |
| amount differs from the transaction | 200, stays `pending`, no access, warning logged |

The gateway always receives `{"ResultCode": 0, "ResultDesc": "Accepted"}` once the
secret is right. Until Step 11 the session start is a no-op placeholder.
Update the status table: Step 9 is done, Step 10 is next.

