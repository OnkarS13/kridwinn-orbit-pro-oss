# Local build: Nuitka standalone -> dist\app.dist, then Inno Setup -> dist\installer
#
# Before running, set these environment variables (same values as the GitHub Actions secrets):
#   KRIDWINN_CONFIG_KEY, KRIDWINN_ACTIVATION_SALT, KRIDWINN_ADMIN_SALT
#   FIREBASE_CREDS_ENC_B64, LICENSING_CONFIG_ENC_B64   (or place the .enc files in secure_config\ yourself)
#
# Usage (from repo root):  powershell -ExecutionPolicy Bypass -File .\build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup (ISCC.exe) not found." }

# 1) Build-time secrets
& $python tools\write_build_secrets.py
if ($LASTEXITCODE -ne 0) { throw "Build secrets are not configured." }
foreach ($f in "secure_config\firebase_creds.enc", "secure_config\licensing_config.enc") {
    if (-not (Test-Path $f)) { throw "Missing $f" }
}

# 2) Nuitka standalone build
if (Test-Path "dist\app.dist") { Remove-Item -Recurse -Force "dist\app.dist" }
& $python -m nuitka --standalone app.py `
    --enable-plugin=pyside6 `
    --include-data-files=secure_config/licensing_config.enc=secure_config/licensing_config.enc `
    --include-data-files=secure_config/firebase_creds.enc=secure_config/firebase_creds.enc `
    --include-data-dir=config=config `
    --include-data-dir=pages=pages `
    --include-data-dir=assets=assets `
    --include-data-files=icon.ico=icon.ico `
    --windows-icon-from-ico=icon.ico `
    --windows-console-mode=disable `
    --output-dir=dist `
    "--output-filename=Kridwinn Orbit Pro.exe" `
    --remove-output --lto=yes --assume-yes-for-downloads --prefer-source-code
if ($LASTEXITCODE -ne 0) { throw "Nuitka build failed ($LASTEXITCODE)" }
if (-not (Test-Path "dist\app.dist\Kridwinn Orbit Pro.exe")) { throw "Built EXE not found" }

# 3) Inno Setup installer
& $iscc "installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed ($LASTEXITCODE)" }

Write-Host "BUILD OK: dist\installer\KridwinnOrbitPro-Setup.exe"
