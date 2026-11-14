# Builds the portable single-file executable:  dist\RecoveryTool.exe
# Usage (PowerShell, from the repository root):  .\build.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade -r requirements.txt pyinstaller pillow
if (-not (Test-Path assets\icon.ico)) { & .\.venv\Scripts\python.exe tools\make_icon.py }

& .\.venv\Scripts\python.exe -m PyInstaller run.py `
    --name RecoveryTool `
    --onefile --windowed --noconfirm --clean `
    --uac-admin `
    --icon assets\icon.ico `
    --add-data "assets\icon.ico;assets" `
    --collect-data customtkinter `
    --version-file tools\version_info.txt

Write-Host ""
Get-Item dist\RecoveryTool.exe | Select-Object Name, @{n='SizeMB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
(Get-FileHash dist\RecoveryTool.exe -Algorithm SHA256).Hash
