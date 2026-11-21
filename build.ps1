# Builds the two portable single-file executables:
#   dist\Benchwise.exe      the window: a window application that starts without administrator
#                           rights and restarts elevated only when a tool needs it
#   dist\Benchwise-cli.exe  the command line: a console program that runs in the terminal it is
#                           started from (no --uac-admin, or Windows would open a new window)
# Usage (PowerShell, from the repository root):  .\build.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade -r requirements.txt pyinstaller
if (-not (Test-Path assets\icon.ico)) { & .\.venv\Scripts\python.exe tools\make_icon.py }

& .\.venv\Scripts\python.exe -m PyInstaller run.py `
    --name Benchwise `
    --onefile --windowed --noconfirm --clean `
    --icon assets\icon.ico `
    --add-data "assets\icon.ico;assets" `
    --collect-data customtkinter `
    --version-file tools\version_info.txt

& .\.venv\Scripts\python.exe -m PyInstaller run_cli.py `
    --name Benchwise-cli `
    --onefile --console --noconfirm `
    --icon assets\icon.ico `
    --exclude-module tkinter --exclude-module customtkinter --exclude-module PIL `
    --version-file tools\version_info.txt

Write-Host ""
foreach ($exe in 'dist\Benchwise.exe', 'dist\Benchwise-cli.exe') {
    Get-Item $exe | Select-Object Name, @{n='SizeMB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
    (Get-FileHash $exe -Algorithm SHA256).Hash
}
