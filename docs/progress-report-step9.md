# WBMS-Lite progress report (before Step 9)

- Steps 1-8 done. Step 8 committed (`5409642`) and pushed on `feature/step-08-start-payment`; 503 tests passed; lint clean.
- Step 9 (slide 68) built in `wbms-step09.zip`: expect 503 + 54 = 557 tests.

## Findings
| # | Finding | Fix |
|---|---|---|
| 1 | My Step 8 test `test_mark_failed_only_moves_pending_transactions` failed on your schema (`CHECK (status = 'success') = (paid_at IS NOT NULL)`). My stand-in schema lacked that rule | A corrected test file is in the zip. Check what you changed with the commands in the reply |
| 2 | The `from wbms.web...` lines were typed into PowerShell and errored | Harmless; they belong in `src\wbms\__init__.py`. Verify with `Select-String src\wbms\__init__.py -Pattern api_payments` |
| 3 | `Invoke-RestMethod` could not connect | The app was not running. Start it first |
| 4 | First `Activate.ps1` failed from `C:\Users\geek` | Run `cd $HOME\Documents\wbms-lite` first |
