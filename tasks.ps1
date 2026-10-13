<#
.SYNOPSIS
    WBMS-Lite task runner for Windows PowerShell (same task names as the Makefile).

.DESCRIPTION
    Run it from anywhere; it always works from the folder it lives in.

.EXAMPLE
    .\tasks.ps1 help
    .\tasks.ps1 venv
    .\tasks.ps1 install
    .\tasks.ps1 test

.NOTES
    Windows PowerShell 5.1 and PowerShell 7 are both supported.
    If Windows says "running scripts is disabled on this system", run once:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    or run a single command like this:
        powershell -ExecutionPolicy Bypass -File .\tasks.ps1 help
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'venv', 'install', 'run', 'test', 'cov', 'lint', 'format', 'initdb', 'clean')]
    [string]$Task = 'help'
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$VenvDir  = '.venv'
$VenvPy   = Join-Path $VenvDir 'Scripts\python.exe'
$FlaskApp = 'wbms:create_app'

# Lets "import wbms" work without installing the package (src layout).
$env:PYTHONPATH = 'src'

$Tasks = [ordered]@{
    help    = 'Show this list of commands'
    venv    = 'Create the .venv virtual environment (once)'
    install = 'Install runtime and dev dependencies into .venv'
    run     = 'Start the Flask dev server in debug mode'
    test    = 'Run the test suite with pytest'
    cov     = 'Run tests with a coverage report; fails below 80 percent'
    lint    = 'Check the code with ruff'
    format  = 'Auto-format the code with ruff'
    initdb  = 'Create the SQLite database from schema.sql'
    clean   = 'Remove caches and coverage output (keeps .venv)'
}

function Invoke-Native {
    # Runs an external program and stops the script with its exit code if it fails.
    param(
        [Parameter(Mandatory)][string]$File,
        [string[]]$Arguments = @()
    )
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED (exit code $LASTEXITCODE): $File $($Arguments -join ' ')" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

function Assert-Venv {
    if (-not (Test-Path -LiteralPath $VenvPy)) {
        Write-Host "No virtual environment in $VenvDir. Run:  .\tasks.ps1 venv" -ForegroundColor Yellow
        exit 1
    }
}

function New-Venv {
    if (Test-Path -LiteralPath $VenvPy) {
        Write-Host "Virtual environment already exists in $VenvDir"
        return
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        Invoke-Native 'py' @('-3.12', '-m', 'venv', $VenvDir)
    }
    else {
        Invoke-Native 'python' @('-m', 'venv', $VenvDir)
    }
    # An offline pip upgrade should not undo a good venv, so this one is not fatal.
    & $VenvPy -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Warning: could not upgrade pip (offline?). The venv itself is fine.' -ForegroundColor Yellow
    }
    Write-Host "Virtual environment ready in $VenvDir"
}

$CacheNames = @('__pycache__', '.pytest_cache', '.ruff_cache', 'htmlcov')

function Remove-CacheDir {
    # Walks the tree but never enters .venv or .git.
    param([Parameter(Mandatory)][string]$Path)
    foreach ($dir in Get-ChildItem -LiteralPath $Path -Directory -Force) {
        if ($dir.Name -eq '.venv' -or $dir.Name -eq '.git') { continue }
        if ($CacheNames -contains $dir.Name) {
            Remove-Item -LiteralPath $dir.FullName -Recurse -Force
            Write-Host "removed $($dir.FullName)"
        }
        else {
            Remove-CacheDir -Path $dir.FullName
        }
    }
}

switch ($Task) {
    'help' {
        Write-Host 'WBMS-Lite tasks (usage: .\tasks.ps1 <task>)'
        Write-Host ''
        foreach ($name in $Tasks.Keys) {
            Write-Host ('  {0,-8} {1}' -f $name, $Tasks[$name])
        }
    }
    'venv' { New-Venv }
    'install' {
        New-Venv
        Invoke-Native $VenvPy @('-m', 'pip', 'install', '-r', 'requirements.txt', '-r', 'requirements-dev.txt')
    }
    'run' {
        Assert-Venv
        Invoke-Native $VenvPy @('-m', 'flask', '--app', $FlaskApp, 'run', '--debug')
    }
    'test' {
        Assert-Venv
        Invoke-Native $VenvPy @('-m', 'pytest', '-v')
    }
    'cov' {
        Assert-Venv
        Invoke-Native $VenvPy @('-m', 'pytest', '--cov=wbms', '--cov-report=term-missing', '--cov-report=html', '--cov-fail-under=80')
    }
    'lint' {
        Assert-Venv
        Invoke-Native $VenvPy @('-m', 'ruff', 'check', '.')
    }
    'format' {
        Assert-Venv
        Invoke-Native $VenvPy @('-m', 'ruff', 'format', '.')
    }
    'initdb' {
        Assert-Venv
        Invoke-Native $VenvPy @('scripts\init_db.py')
    }
    'clean' {
        Remove-CacheDir -Path (Get-Location).Path
        Remove-Item -LiteralPath '.coverage' -Force -ErrorAction SilentlyContinue
        Write-Host 'Clean.'
    }
}
