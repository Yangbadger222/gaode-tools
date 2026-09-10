$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python launcher not found. Install Python 3.12 x64 first." }
if (-not (Test-Path ".venv")) { py -3.12 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Write-Host "Copy .env.example to .env and configure AMAP_JS_API_KEY if needed."
& .\.venv\Scripts\python.exe scripts\diagnose_environment.py
