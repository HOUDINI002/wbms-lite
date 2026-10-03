# Python virtual environment cheat sheet

A virtual environment is an isolated folder holding its own Python interpreter and installed packages, so each project keeps its own dependencies and doesn't clash with other projects or the system Python. When active, your prompt starts with `(.venv)`.

## Windows PowerShell
```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # only if activation is blocked
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Get-Command python | Select-Object -ExpandProperty Source    # should end in .venv\Scripts\python.exe
deactivate
```

## macOS / Linux
```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
which python        # should end in .venv/bin/python
deactivate
```

## Recreate from scratch if it breaks
PowerShell:
```powershell
deactivate
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```
macOS / Linux:
```bash
deactivate
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

Never copy or move a .venv folder; recreate it. Add `.venv/` to .gitignore.
