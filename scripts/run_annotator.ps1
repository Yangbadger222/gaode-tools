param(
    [string]$Folder = "",
    [string]$Region = "",
    [ValidateSet("zh", "en")][string]$Language = "zh"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Virtual environment not found. Run scripts\setup_windows.ps1 first."
}

$Arguments = @("scripts\launch_annotator.py", "--language", $Language)
if ($Folder) { $Arguments += @("--folder", $Folder) }
if ($Region) { $Arguments += @("--region", $Region) }
& $Python @Arguments
