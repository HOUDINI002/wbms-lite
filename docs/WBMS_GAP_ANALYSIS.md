# WBMS-Lite: Gap Analysis and Status Report (v2)

Updated 3 Oct 2026, about 4:40 PM. New evidence in this version: your PowerShell history (`Powershel.txt`), your `README.md`, and the 4:17 PM Explorer screenshot with hidden items shown. Earlier sources still apply: the 100-slide deck, the chat export, and the first two screenshots.

## 1. What changed since v1

| v1 finding | Status now | Evidence |
|---|---|---|
| A. `.gitignore` named `gitignore` | **Fixed** | `Rename-Item gitignore .gitignore` worked. `git status` no longer lists `.venv`, `__pycache__` or `.pytest_cache`, so the file is doing its job. |
| B. Code loose in the root | **Still open, and now two new traps** | `Move-Item` failed, and the workaround created a **folder** named `phone.py` (section 4). |
| C. Requirement pins unverified | **Verified** | A clean rebuild installed all 9 pinned packages (section 3). |
| D. gunicorn will not run on Windows | Unchanged | Installs fine. Keep it for the Docker step. |
| E. Git state unknown | **Resolved** | `.git` is visible and `git status` works. A README commit most likely exists (section 5). |
| Scaffold not yet run | **Still not run** | `scaffold.py` is in the project root, not `scripts/`. No `docs/`, `tests/` or `scripts/` folders exist yet. |

One correction of my own. The `Move-Item` errors came from a sequencing flaw in v1: it listed the move commands (issue B) before the step that creates their destination folders (section 6). Section 4 below puts everything in one ordered block.

## 2. Bottom line

| Question | Answer |
|---|---|
| Where are you in the deck? | Slide 44 of 100 (Module 2, the scaffold prompt). Unchanged. |
| Course prompts done | **5 of 45 confirmed** (slides 7, 36, 41 twice, and 44 delivered), plus slide 35 (Git repo) partly. About 11 to 13%. |
| Lab 1 (slide 48) | About **45%**. It was about 35% in v1. After the section 4 recovery and a few commits, about 75%. |
| Slide-25 tree present on disk | About 10%: `README.md`, the two requirements files, and an empty `src/wbms/`. |
| Application code | 0 of 20 build steps. The only real code is `phone.py` and its test. |
| Estimated effort to a working, tested system | **About 8 to 10%.** Same weighting as v1: infrastructure 10%, planning 5%, build 55%, tests 20%, ship 10%. |

Progress this session was real but mostly environment work. The environment is now clean and verified. The structure is not built yet.

## 3. What the PowerShell history shows

### Worked

| Command | Result |
|---|---|
| `Rename-Item gitignore .gitignore` | File renamed (2,101 bytes). |
| `pip install -r requirements-dev.txt` (run **before** activating the venv) | "Requirement already satisfied" in `...\Python312\Lib\site-packages`. See note below. |
| `pip check` (global, then venv) | "No broken requirements found." both times. |
| `.\.venv\Scripts\Activate.ps1` | Worked. Prompt shows `(.venv)`. |
| `Get-Command python ...` / `python --version` | `...\wbms-lite\.venv\Scripts\python.exe`, **Python 3.12.10**. |
| `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` | Accepted. Applies to that window only. |
| `Remove-Item -Recurse -Force .venv`, `py -3.12 -m venv .venv`, install | **Clean rebuild succeeded** (3:48 PM). |
| `git status --short` | Works, so a repo exists. |

The clean rebuild installed exactly: Flask 3.0.3, python-dotenv 1.0.1, requests 2.32.5, gunicorn 23.0.0, pytest 8.3.5, pytest-cov 5.0.0, freezegun 1.5.5, responses 0.25.8, ruff 0.6.9, plus their dependencies. **Every pin resolves, so v1 issue C is closed.** It also shows a fresh clone can rebuild the environment from the two requirements files, which is the first half of the Lab 1 pass test.

Note: the first `pip install` ran outside the venv, so the same packages are also in your global Python 3.12. That is harmless, but it can hide a missing dependency (a test passes globally and fails for a classmate). Always see `(.venv)` in the prompt before running pip or pytest.

### Failed

| What you ran | What happened | Why | Correct command |
|---|---|---|---|
| `task.ps1`, then `tasks.ps1` | "not recognized" | Two causes. The file does not exist yet (I have not delivered it; it is the next deliverable). PowerShell also does not run scripts from the current folder by bare name. | `.\tasks.ps1`, once the file exists |
| `deactivate` (second time) | "not recognized" | The first `deactivate` had already left the venv. Harmless. | Run it once, only when `(.venv)` is showing |
| `pip install -r requirements-dev.txt.\.venv\Scripts\Activate.ps1` | "Could not open requirements file" | Two commands were pasted onto one line (a missing line break). | One command per line. The next paste worked. |
| `Move-Item phone.py src\wbms\phone.py` | "Could not find a part of the path" | `src\wbms\` did not exist. The scaffold, which creates it, had not been run. | After the scaffold (section 4) |
| `Move-Item test_phone.py tests\unit\test_phone.py` | Same error | `tests\unit\` did not exist. | Same |
| `mkdr src` | "not recognized" | Typo. | `mkdir src` |
| `mkdir` with no arguments, typing `y` | Created a stray folder **`y`** | Bare `mkdir` prompts for a path, and `y` became the folder name. | `Remove-Item y` |
| `remove y` | "not recognized" | `remove` is not a command. | `Remove-Item y` |
| `mkdir` with two paths at the prompt | First path "already exists". The second created `src\wbms\phone.py` as a **folder**. | Bare `mkdir` accepts several paths and creates every one of them as a directory. | See trap 1 below |

**Trap 1: `src\wbms\phone.py` is a folder, not a file.** The listing shows `d-----` for it, and `cd phone.py` worked. If you run `Move-Item phone.py src\wbms\phone.py` now, PowerShell moves the file **inside** that folder, giving `src\wbms\phone.py\phone.py`, and imports will break. Delete the empty folder first.

**Trap 2: `scaffold.py` in the project root.** My v1 script guessed the project root as the folder above `scripts/`. Run from your root, that guess is `C:\Users\geek\Documents`, and it would have created about 40 files and folders in your Documents folder. I have fixed this in the updated `scaffold.py`. It now refuses to guess unless it sits in a `scripts/` folder, or you pass `--root .`. The updated `test_scaffold.py` also loads from either location. Replace both old copies with the new ones.

## 4. Current state of the folder, and the recovery block

### Folder as of 4:17 PM (screenshot, 16 items, hidden items shown)

| Item | State |
|---|---|
| `.git` (3:40 PM) | Repository exists. |
| `.venv` (3:48 PM) | Rebuilt clean, Python 3.12.10, all dependencies installed. |
| `.pytest_cache`, `__pycache__` | Caches. Git-ignored. |
| `.gitignore` | Correct name, 2,101 bytes. Untracked at the last status check. |
| `README.md` | 3 lines (section 6). |
| `requirements.txt`, `requirements-dev.txt` | Good. Untracked at the last status check. |
| `VENV_COMMANDS.md` | Good. Untracked. |
| `phone.py`, `test_phone.py` | Still in the root. They belong in `src/wbms/` and `tests/unit/`. |
| `scaffold.py`, `test_scaffold.py` | In the root, and the old v1 copies. |
| `WBMS_GAP_ANALYSIS.md` | The v1 report, in the root. |
| **`src/`** (4:13 PM) | Contains only `wbms/`. See the next table. |
| **`y/`** (4:04 PM) | Stray empty folder. Delete it. |

### `src/wbms/` state, explicitly

| Expected (slide 25) | Actually there |
|---|---|
| `__init__.py`, `config.py`, `db.py`, `schema.sql`, `cli.py` | **None.** |
| `repositories/`, `services/`, `gateways/` (with `payments/`, `routers/`), `web/` | **None.** |
| `phone.py` (our helper, a file) | An **empty folder** named `phone.py`. |

Missing at the project level: `scripts/`, `docs/`, `tests/`, `Makefile`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.env.example`.

### Recovery block (run in this order)

Run the steps in order. Pause at the two steps marked "manual", where you save a downloaded file before continuing.

```powershell
# You are currently inside src\wbms\phone.py. Go back to the root.
cd C:\Users\geek\Documents\wbms-lite
.\.venv\Scripts\Activate.ps1

# 1. Remove the two accidental folders
Remove-Item y
Remove-Item src\wbms\phone.py          # the EMPTY FOLDER; the real phone.py file is still in the root

# 2. Install the NEW scaffold (manual)
New-Item -ItemType Directory -Force scripts | Out-Null
#    -> save the new scaffold.py as  scripts\scaffold.py
Remove-Item scaffold.py                # old root copy

# 3. Preview, then build the tree
python scripts\scaffold.py --dry-run
python scripts\scaffold.py

# 4. Install the NEW tests (manual)
#    -> save the new test_scaffold.py as  tests\unit\test_scaffold.py
Remove-Item test_scaffold.py           # old root copy

# 5. Move your phone helper and its test into place
Move-Item phone.py      src\wbms\phone.py
Move-Item test_phone.py tests\unit\test_phone.py
Move-Item WBMS_GAP_ANALYSIS.md docs\   # or save this v2 into docs\ and delete the root copy

# 6. Fix the import in tests\unit\test_phone.py (open it in VS Code):
#      from phone import normalize_phone     ->     from wbms.phone import normalize_phone
#    (use your function's real name if it differs)

# 7. Run everything
python -m pytest -v
```

What to expect at step 3: about 41 items created and about 7 skipped (the root, `scripts/`, `src/`, `src/wbms/`, `README.md` and the two requirements files). Your `README.md` and requirements files are never touched. Step 7 should pass `test_phone.py` and all of `test_scaffold.py`. The scaffolded `pyproject.toml` already contains `pythonpath = ["src"]`, which is what makes `from wbms.phone import ...` work.

I checked this exact sequence on a copy of your layout, including the stray `y` folder, the `phone.py` folder, and the loose scripts. The sequence works and nothing was written outside the project folder.

## 5. Git state

- **A repository exists** (`.git` visible; `git status --short` works).
- **At least one commit very likely exists.** In the status check, `README.md` was **not** listed as untracked, while every other file was. The simplest explanation is that it is already committed. That is an inference, not something I can see directly.
- **The `.gitignore` is working.** `.venv`, `__pycache__` and `.pytest_cache` do not appear in the status.
- **A newer commit is possible.** `.git` was modified at 3:40 PM, and I only have the status output, so check `git log --oneline` for the real count.
- **Remote unknown.** Check `git remote -v`. Lab 1 needs a GitHub repo and a pull request.

Lab 1 asks for 4 or more small commits and one PR. A sequence that gets you there, using the Conventional Commits style from slide 38 (run `git status` before each `add`):

```powershell
git branch --show-current              # note your default branch (main?)
git switch -c feature/project-skeleton

git add .gitignore requirements.txt requirements-dev.txt
git commit -m "chore: add gitignore and pinned requirements"

git add VENV_COMMANDS.md
git commit -m "docs: add virtual environment commands"

git add scripts/scaffold.py tests/unit/test_scaffold.py
git commit -m "feat(scripts): add project scaffold script with tests"

git add src/wbms/phone.py tests/unit/test_phone.py
git commit -m "feat(phone): add phone number normalizer with tests"

git status --short                     # review what is left
git add -A
git commit -m "chore: scaffold wbms-lite project tree"

# only if no remote exists yet:
#   gh auth login
#   gh repo create wbms-lite --public --source . --push
git push -u origin feature/project-skeleton
gh pr create --fill
```

## 6. README review

Your `README.md` is three lines: the title `# wbms-lite` and "A lightweight version of the WBMS project."

| Slide 33 requirement | Present? |
|---|---|
| What it is | Barely. It does not say it is a WiFi billing system, or what "WBMS" stands for. |
| Prerequisites (Python 3.12, Git) | No |
| Setup (venv, install) | No. Those commands are in `VENV_COMMANDS.md`. |
| How to run | No (nothing runs yet) |
| How to test | No |
| Folder map | No |

It fails the slide-33 pass test (a classmate runs the project from the README alone in under 10 minutes). It is a quick win: the setup, test and folder-map sections can be written now from facts we already verified. I can generate it next. The scaffold will skip it, since it exists.

## 7. Lab 1 checklist (slide 48), updated

| Lab step | v1 | Now |
|---|---|---|
| Create the GitHub repository and clone it | Unknown | Local repo exists. Remote unconfirmed. |
| Generate the tree with the scaffold prompt | Ready | **Not run.** Misplaced, with two traps. Section 4 fixes it. |
| Add `.gitignore`, `.env.example`, README, requirements files | `.gitignore` misnamed | `.gitignore` fixed. Requirements fine. README too thin. `.env.example` comes from the scaffold. |
| Create the venv and install dependencies | Probably done | **Done and proven** by a clean rebuild. |
| 4 or more commits and 1 pull request | Unknown | At least 1 commit (inferred). No PR yet. |
| Pass test: a classmate gets a working environment in under 10 minutes | Not yet | The environment half passes. The README half does not. |

## 8. Roadmap to a working, tested system

Unchanged from v1 except Lab 1. Prompt counts are for the deck's code-gen prompts in that phase.

| Phase | Deck slides | Prompts | Status |
|---|---|---|---|
| Orientation example (phone normalizer) | 7 | 2 (1 done, 1 template) | Done |
| Lab 1: skeleton | 35 to 44, 48 | 6 (4 done) | **About 45%** |
| Task runner | 45 | 1 | Next. Not delivered yet; `tasks.ps1` does not exist. |
| Module 3: Plan | 50 to 58 | 0 | Not started (docs only) |
| M1 Foundation | 60 to 62 | 5 | Not started |
| M2 Catalog | 63 to 65 | 3 | Not started |
| M3 Payments | 66 to 69 | 6 | Not started |
| M4 Access | 70 to 74 | 6 | Not started |
| M5 Admin and vouchers | 75 to 79 | 6 | Not started |
| Module 5: Testing | 84 to 93 | 8 | Not started |
| Module 6: Ship | 96 to 100 | 2 | Not started |

Deck inconsistencies from v1 still apply: slide 59 says "Twenty-one" steps while the slides show 20, and slide 25's tree omits `workers/`, `tests/e2e/` and `.github/workflows/`, which later slides add.

## 9. Toolchain check (slide 8)

| Tool | Status |
|---|---|
| Python 3.12 | Confirmed, 3.12.10 in the venv |
| pip and venv | Confirmed |
| Git | Confirmed (`git status` works) |
| VS Code | Likely (its icon is on your taskbar) |
| Docker Desktop, ngrok, Daraja sandbox | Not checked. Not needed until slides 93 and 96. |

## 10. What I verified, and what I could not

**Verified:**
- 42 test cases pass on Python 3.12 and 3.13 (38 in v1). The new ones cover script location: the script refuses to guess its root outside `scripts/`, uses the parent folder when inside `scripts/`, writes nothing when it refuses, and works with `--root .`.
- The full recovery sequence ran on a copy of your layout (stray `y`, the `phone.py` folder, scripts loose in the root).
- Every claim about your terminal history comes from the log lines. The Git inferences in section 5 are labeled as inferences.

**Not verified:**
- Real pytest. Its package index is blocked in my workspace, so I ran the tests under a small stand-in for pytest. Your first `python -m pytest -v` is the real check. Tell me if anything differs.
- The contents of `phone.py`, `test_phone.py` and `.gitignore`, which I have not seen. The import fix in step 6 assumes your function is named `normalize_phone`.
- The GitHub remote, and the real commit count.

## 11. Next steps

1. Run the section 4 recovery block, then `python -m pytest -v`.
2. Make the section 5 commits and open the pull request.
3. Replace the README with a real one (I can generate it).
4. Then slide 45: I will deliver `tasks.ps1`, which you run as `.\tasks.ps1 <task>`, because you do not have `make` on Windows.
5. Then Module 3 docs, then Step 1 (slide 60).
