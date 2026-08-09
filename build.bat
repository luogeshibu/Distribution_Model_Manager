@echo off
setlocal
cd /d "%~dp0"

echo.
echo =========================================
echo  Distribution Model Manager Build
echo =========================================
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build completed successfully.
echo Release package:
echo   %~dp0Release
echo.
pause
endlocal
