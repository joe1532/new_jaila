@echo off
setlocal

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
echo [2/2] Deployer frontend...
cd Frontend
call DEPLOY_CLEAN_START.bat
cd ..
if errorlevel 1 (
  echo Frontend deployment fejlede.
  goto :done
)

echo.
echo ========================================
echo   Deployment fuldfort.
echo ========================================
echo.

:done
endlocal
pause
