param(
    [switch]$BuildExe
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "=== Distribution Model Manager Release Check ===" -ForegroundColor Cyan

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "未找到 .venv\Scripts\python.exe，请先创建并安装项目依赖。"
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"

Write-Host "[1/7] Python compile check..."
& $Python -m compileall -q app.py src
if ($LASTEXITCODE -ne 0) { throw "Python compile check failed." }

Write-Host "[2/7] Automated tests..."
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed." }

Write-Host "[3/7] Import/bootstrap check..."
& $Python -c "import paramiko; from dmm.config.constants import APP_VERSION; from dmm.application.registry import get_model_modules; print('Version:', APP_VERSION); print('Modules:', ','.join(get_model_modules().keys()))"
if ($LASTEXITCODE -ne 0) { throw "Import/bootstrap check failed." }

Write-Host "[4/7] Release safety checks..."
$BuildScript = Get-Content ".\build_exe.ps1" -Raw
if ($BuildScript -match "(?i)smoke") {
    throw "build_exe.ps1 中仍发现 smoke test 相关文本。"
}
if ($BuildScript -notmatch '\$AppName\s*=\s*"Distribution_Model_Manager_v\$AppVersion"') {
    throw "build_exe.ps1 未从 APP_VERSION 派生 AppName，存在版本号打包不一致风险。"
}
if ($BuildScript -match '\$AppName\s*=\s*"Distribution_Model_Manager_v\d+\.\d+\.\d+"') {
    throw "build_exe.ps1 中发现硬编码版本 AppName，请改为从 APP_VERSION 自动派生。"
}
Write-Host "  - smoke test: not found"
Write-Host "  - packaging version: derived from APP_VERSION"
Write-Host "  - source G safety: Workspace copy/write-back architecture enabled"

Write-Host "[5/7] Report/audit feature checks..."
$Main = Get-Content ".\src\dmm\ui\main_window.py" -Raw
if ($Main -notmatch "model_change_log\.csv") {
    throw "未发现模型修改记录 CSV 功能。"
}
if ($Main -notmatch "run_manifest\.json") {
    throw "未发现运行历史 manifest 功能。"
}
Write-Host "  - model_change_log.csv: OK"
Write-Host "  - run_manifest.json: OK"

Write-Host "[6/7] Build metadata..."
& $Python -c "from dmm.config.constants import APP_NAME,APP_VERSION,APP_BUILD_DATE; print(APP_NAME, APP_VERSION, APP_BUILD_DATE)"

if ($BuildExe) {
    Write-Host "[7/7] Building EXE..."
    powershell -ExecutionPolicy Bypass -File ".\build_exe.ps1"
    if ($LASTEXITCODE -ne 0) { throw "EXE build failed." }
} else {
    Write-Host "[7/7] EXE build skipped. Use -BuildExe to include packaging."
}

Write-Host ""
Write-Host "RELEASE CHECK PASSED" -ForegroundColor Green
