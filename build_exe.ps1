$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$BuildScriptVersion = "3.0.23"
$AppName = "Distribution_Model_Manager_v3.0.23"

$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

$BuildDir = Join-Path $ProjectRoot "build"
$DistDir = Join-Path $ProjectRoot "dist"
$DistAppDir = Join-Path $DistDir $AppName

$ReleaseDir = Join-Path $ProjectRoot "release"
$ReleaseZip = Join-Path $ReleaseDir "$AppName.zip"

$IconPath = Join-Path $ProjectRoot "src\dmm\resources\app_logo.ico"

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

Write-Host ""
Write-Host "============================================================"
Write-Host " Distribution Model Manager Build"
Write-Host " Build script version : $BuildScriptVersion"
Write-Host " Script path          : $($MyInvocation.MyCommand.Path)"
Write-Host " Project root         : $ProjectRoot"
Write-Host " Target               : $AppName"
Write-Host "============================================================"
Write-Host ""

Write-Host "[1/6] Checking virtual environment..."

if (!(Test-Path $VenvPython)) {
    New-ProjectVenv
}

try {
    & $VenvPython -c "import sys; print(sys.executable)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        New-ProjectVenv
    }
}
catch {
    New-ProjectVenv
}

Write-Host "[2/6] Installing dependencies..."

& $VenvPython -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) {
    throw "ensurepip failed."
}

& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "pip tooling upgrade failed."
}

& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "requirements installation failed."
}

Write-Host "[3/6] Verifying Python dependencies..."

& $VenvPython -c "import getpass, ssl, socket, secrets, oracledb, cryptography, cffi, _cffi_backend, PySide6; print('Dependencies OK'); print('oracledb=', oracledb.__version__); print('cryptography=', cryptography.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency verification failed."
}

if (!(Test-Path $IconPath)) {
    throw "Application icon not found: $IconPath"
}

Write-Host "[4/6] Cleaning old build output..."

if (Test-Path $BuildDir) {
    Remove-Item $BuildDir -Recurse -Force
}
if (Test-Path $DistDir) {
    Remove-Item $DistDir -Recurse -Force
}
if (Test-Path $ReleaseDir) {
    Remove-Item $ReleaseDir -Recurse -Force
}

Write-Host "[5/6] Building EXE..."

& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --paths "src" `
    --name "$AppName" `
    --icon "$IconPath" `
    --add-data "src\dmm\resources;dmm\resources" `
    --additional-hooks-dir "hooks" `
    --hidden-import "getpass" `
    --hidden-import "ssl" `
    --hidden-import "socket" `
    --hidden-import "secrets" `
    --hidden-import "oracledb" `
    --hidden-import "cryptography" `
    --hidden-import "cffi" `
    --hidden-import "_cffi_backend" `
    --hidden-import "cryptography.hazmat" `
    --hidden-import "cryptography.hazmat.primitives" `
    --hidden-import "cryptography.hazmat.primitives.ciphers" `
    --hidden-import "cryptography.hazmat.primitives.kdf" `
    --hidden-import "dmm.application.modules.rmu" `
    --hidden-import "dmm.application.modules.feeder" `
    --collect-all "oracledb" `
    --collect-all "cryptography" `
    --collect-all "cffi" `
    --copy-metadata "oracledb" `
    --copy-metadata "cryptography" `
    app.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

if (!(Test-Path $DistAppDir)) {
    throw "PyInstaller output not found: $DistAppDir"
}

$DistExe = Join-Path $DistAppDir "$AppName.exe"
if (!(Test-Path $DistExe)) {
    throw "Built EXE not found: $DistExe"
}

$OracleMatches = Get-ChildItem -Path $DistAppDir -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "oracledb" }

if (!$OracleMatches -or $OracleMatches.Count -eq 0) {
    throw "No oracledb files found in packaged output."
}

$CryptoMatches = Get-ChildItem -Path $DistAppDir -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "cryptography" }

if (!$CryptoMatches -or $CryptoMatches.Count -eq 0) {
    throw "No cryptography files found in packaged output."
}

$CffiMatches = Get-ChildItem -Path $DistAppDir -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "cffi" }

$CffiBackendMatches = Get-ChildItem -Path $DistAppDir -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "^_cffi_backend.*\.(pyd|dll)$" }

if (!$CffiMatches -or $CffiMatches.Count -eq 0) {
    throw "No cffi package files found in packaged output."
}

if (!$CffiBackendMatches -or $CffiBackendMatches.Count -eq 0) {
    throw "_cffi_backend binary was not found in packaged output."
}

Write-Host "oracledb packaged files     : $($OracleMatches.Count)"
Write-Host "cryptography packaged files : $($CryptoMatches.Count)"
Write-Host "cffi packaged files         : $($CffiMatches.Count)"
Write-Host "_cffi_backend binary files  : $($CffiBackendMatches.Count)"

Write-Host "[6/6] Creating Release..."

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null

if (Test-Path $ReleaseZip) {
    Remove-Item $ReleaseZip -Force
}

$ZipScript = @'
import sys
import zipfile
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])

with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for item in source.rglob("*"):
        if item.is_file():
            archive.write(item, item.relative_to(source.parent))

print(target)
'@

$TempZipScript = Join-Path $env:TEMP "dmm_release_zip.py"
[System.IO.File]::WriteAllText(
    $TempZipScript,
    $ZipScript,
    [System.Text.Encoding]::UTF8
)

& $VenvPython $TempZipScript $DistAppDir $ReleaseZip
$ZipExitCode = $LASTEXITCODE

Remove-Item $TempZipScript -Force -ErrorAction SilentlyContinue

if ($ZipExitCode -ne 0) {
    throw "release ZIP creation failed."
}

if (!(Test-Path $ReleaseZip)) {
    throw "release ZIP not found: $ReleaseZip"
}

Write-Host ""
Write-Host "============================================================"
Write-Host " BUILD COMPLETE"
Write-Host "============================================================"
Write-Host "EXE:"
Write-Host "  $DistExe"
Write-Host ""
Write-Host "release ZIP:"
Write-Host "  $ReleaseZip"
Write-Host ""
Write-Host "IMPORTANT:"
Write-Host "  This build script NEVER executes the generated EXE."
Write-Host "============================================================"
