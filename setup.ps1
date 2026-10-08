param(
    [switch]$NoRun
)

$ErrorActionPreference = "Stop"

# Always run from the project root where this script is located.
Set-Location $PSScriptRoot

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Distribution Model Manager - Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

function Test-Python311OrNewer {
    param(
        [string]$Command,
        [string[]]$PrefixArgs = @()
    )

    try {
        $versionText = & $Command @PrefixArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        if (-not $versionText) {
            return $false
        }

        $parts = $versionText.Trim().Split(".")
        $major = [int]$parts[0]
        $minor = [int]$parts[1]

        return ($major -gt 3) -or ($major -eq 3 -and $minor -ge 11)
    }
    catch {
        return $false
    }
}

$PythonCommand = $null
$PythonPrefixArgs = @()

# Prefer the Windows Python Launcher. "py -3" selects the newest installed
# Python 3, then we verify that it is Python 3.11 or newer.
if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python311OrNewer -Command "py" -PrefixArgs @("-3")) {
        $PythonCommand = "py"
        $PythonPrefixArgs = @("-3")
    }
}

# Fall back to the default "python" command.
if (-not $PythonCommand -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Python311OrNewer -Command "python") {
        $PythonCommand = "python"
        $PythonPrefixArgs = @()
    }
}

if (-not $PythonCommand) {
    Write-Host "ERROR: Python 3.11 or newer was not found." -ForegroundColor Red
    Write-Host "Please install Python 3.11+ and make sure 'py' or 'python' is available in PATH." -ForegroundColor Yellow
    exit 1
}

$PythonVersion = & $PythonCommand @PythonPrefixArgs -c "import sys; print(sys.version.split()[0])"
Write-Host "[1/6] Python detected: $PythonVersion" -ForegroundColor Green

$VenvDir = Join-Path $PSScriptRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[2/6] Creating virtual environment: .venv" -ForegroundColor Cyan
    & $PythonCommand @PythonPrefixArgs -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create .venv." -ForegroundColor Red
        exit 1
    }
}
else {
    Write-Host "[2/6] Existing virtual environment found: .venv" -ForegroundColor Green
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: Failed to create .venv." -ForegroundColor Red
    exit 1
}

Write-Host "[3/6] Upgrading pip/setuptools/wheel..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to upgrade Python packaging tools." -ForegroundColor Red
    exit 1
}

$Requirements = Join-Path $PSScriptRoot "requirements.txt"
if (-not (Test-Path $Requirements)) {
    Write-Host "ERROR: requirements.txt was not found in:" -ForegroundColor Red
    Write-Host "       $PSScriptRoot" -ForegroundColor Red
    exit 1
}

Write-Host "[4/6] Installing project dependencies..." -ForegroundColor Cyan
& $VenvPython -m pip install -r $Requirements
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install project dependencies." -ForegroundColor Red
    exit 1
}

Write-Host "[5/6] Verifying core dependencies..." -ForegroundColor Cyan
& $VenvPython -c "import PySide6, oracledb, cryptography, paramiko, cffi; print('Dependencies OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Dependency verification failed." -ForegroundColor Red
    exit 1
}

Write-Host "[6/6] Setup completed successfully." -ForegroundColor Green
Write-Host "Virtual environment: $VenvDir" -ForegroundColor Green
Write-Host ""

if (-not $NoRun) {
    $AppPath = Join-Path $PSScriptRoot "app.py"
    if (-not (Test-Path $AppPath)) {
        Write-Host "ERROR: app.py was not found." -ForegroundColor Red
        exit 1
    }

    Write-Host "Starting Distribution Model Manager..." -ForegroundColor Cyan
    & $VenvPython $AppPath
}
else {
    Write-Host "Application launch skipped because -NoRun was specified." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
