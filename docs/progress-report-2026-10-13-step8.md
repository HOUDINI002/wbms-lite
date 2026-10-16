# WBMS-Lite progress report, 13 Oct 2026 (before Step 8)

## Where you are
- Steps 1-7 done. Step 7 is committed (`9ca2243`) and pushed on `feature/step-07-payment-gateway`; 425 tests passed.
- Milestone M3 (Payments) is in progress: gateway interface and mock done; payment start (Step 8, slide 67) is the next build.
- `.env` is not tracked (`git ls-files .env` printed nothing).

## Things to fix or check
| # | Finding (from your PowerShell log and folder screenshot) | Fix |
|---|---|---|
| 1 | `.\\.venv\Scripts\Activate.ps1` (double backslash) failed. It worked after `cd` into the project and retyping | Use one backslash: `.\.venv\Scripts\Activate.ps1` |
| 2 | `git switch main` was refused: local changes to `gateways/payments/__init__.py`. Step 7 was built on the current branch, which is stacked on the Step 4-6 work | Nothing to undo. Open the PR for the Step 7 branch; it carries Steps 4-7 |
| 3 | `.\tasks.ps1 lint` was not run before the Step 7 commit (only pytest) | Run it now; if it complains: `python -m ruff check --fix src tests` |
| 4 | `README.md` was not part of the Step 7 commit (not in the file list; screenshot shows it unchanged since 12 Oct) | Append `docs/readme-steps7-8-snippet.md` once (it covers Steps 7 and 8) |
| 5 | LF to CRLF warnings on `git add` | Harmless, leave them |
| 6 | `git pull` on the new branch: no tracking info | Already fixed by `git push -u origin HEAD` |
| 7 | Step 8 needs a MAC on the transaction, but the schema has none | `python scripts\add_mac_to_transactions.py` and add the column to `schema.sql` |
