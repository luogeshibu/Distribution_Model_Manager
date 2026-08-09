$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$AppName = "Distribution_Model_Manager_v2.8.0"
$VenvDir = Join-Path $PSScriptRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$DistDir = Join-Path $PSScriptRoot "dist"
$BuildDir = Join-Path $PSScriptRoot "build"
$ReleaseDir = Join-Path $PSScriptRoot "Release"
$DistAppDir = Join-Path $DistDir $AppName
$ReleaseAppDir = Join-Path $ReleaseDir $AppName
$ReleaseZip = Join-Path $ReleaseDir "$AppName.zip"

Write-Host ""
Write-Host "========================================="
Write-Host " Distribution Model Manager Build"
Write-Host " $AppName"
Write-Host "========================================="
Write-Host ""

function New-ProjectVenv {
    if (Test-Path $VenvDir) {
        Remove-Item $VenvDir -Recurse -Force
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $VenvDir
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $VenvDir
    }
    else {
        throw "Python 3 was not found."
    }

    if ($LASTEXITCODE -ne 0 -or !(Test-Path $VenvPython)) {
        throw "Failed to create virtual environment."
    }
}

Write-Host "[1/6] Checking virtual environment..."

$NeedRecreate = $false
if (!(Test-Path $VenvPython)) {
    $NeedRecreate = $true
}
else {
    try {
        & $VenvPython -c "import sys; print(sys.executable)" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $NeedRecreate = $true
        }
    }
    catch {
        $NeedRecreate = $true
    }
}

if ($NeedRecreate) {
    New-ProjectVenv
}

Write-Host "[2/6] Checking pip..."
try {
    & $VenvPython -m pip --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        New-ProjectVenv
        & $VenvPython -m ensurepip --upgrade
    }
}
catch {
    New-ProjectVenv
    & $VenvPython -m ensurepip --upgrade
}

Write-Host "[3/6] Installing dependencies..."
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }

& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install requirements." }

Write-Host "[4/6] Cleaning previous build..."
if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
if (Test-Path $ReleaseDir) { Remove-Item $ReleaseDir -Recurse -Force }
New-Item -ItemType Directory -Path $ReleaseDir | Out-Null

Write-Host "[5/6] Building application..."
& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name $AppName `
    --icon "assets\app_logo.ico" `
    --add-data "assets;assets" `
    --add-data "config.json;." `
    --hidden-import "modules.rmu" `
    --hidden-import "modules.feeder" `
    app.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}
if (!(Test-Path $DistAppDir)) {
    throw "PyInstaller output not found: $DistAppDir"
}

Write-Host "[6/6] Preparing Release..."
Copy-Item -Path $DistAppDir -Destination $ReleaseAppDir -Recurse -Force

# Avoid PowerShell Compress-Archive file-lock problems.
$ZipScript = @'
import os
import sys
import time
import zipfile
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])

last_error = None
for attempt in range(1, 6):
    try:
        if target.exists():
            target.unlink()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in source.rglob("*"):
                if item.is_file():
                    zf.write(item, item.relative_to(source.parent))
        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError("ZIP file was not created correctly.")
        print(f"ZIP created: {target}")
        sys.exit(0)
    except Exception as exc:
        last_error = exc
        print(f"ZIP attempt {attempt}/5 failed: {exc}")
        time.sleep(1.5)

raise SystemExit(f"ZIP creation failed after retries: {last_error}")
'@

$TempZipPy = Join-Path $env:TEMP "dmm_build_zip.py"
[System.IO.File]::WriteAllText($TempZipPy, $ZipScript, [System.Text.Encoding]::UTF8)

& $VenvPython $TempZipPy $ReleaseAppDir $ReleaseZip
$ZipExitCode = $LASTEXITCODE
Remove-Item $TempZipPy -Force -ErrorAction SilentlyContinue

if ($ZipExitCode -ne 0) {
    throw "Release ZIP creation failed."
}

$ReleaseExe = Join-Path $ReleaseAppDir "$AppName.exe"
if (!(Test-Path $ReleaseExe)) {
    throw "Release EXE not found: $ReleaseExe"
}
if (!(Test-Path $ReleaseZip)) {
    throw "Release ZIP not found: $ReleaseZip"
}

Write-Host ""
Write-Host "========================================="
Write-Host " Build completed successfully"
Write-Host "========================================="
Write-Host "Application: $ReleaseAppDir"
Write-Host "Release ZIP: $ReleaseZip"
