@echo off
setlocal
set SKIP_PAUSE=1

echo.
echo ========================================
echo   JAILA - Fuldt Deployment
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] Deployer backend...
call backend\deploy\DEPLOY_BACKEND.bat
if errorlevel 1 (
  echo Backend deployment fejlede.
  goto :done
)

echo.
echo [2/2] Frontend er JAILA-NEW-FRONTEND, ikke denne mappe.
echo Koer DEPLOY_V2.bat der. DEPLOY_CLEAN_START.bat er slaaet fra,
echo saa den ikke laegger gammel JAILA tilbage paa forsiden.

echo.
echo ========================================
echo   Backend-deployment fuldfort.
echo ========================================
echo.

:done
endlocal
if not defined SKIP_PAUSE pause
