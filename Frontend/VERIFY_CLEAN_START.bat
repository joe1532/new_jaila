@echo off
setlocal

echo.
echo ========================================
echo   JAILA Clean-Start Verify
echo ========================================
echo.

set "BASE_URL=https://skat-chat.dk/clean-start"
set "HEALTH_URL=https://skat-chat.dk/api/health"

set "TMP_DIR=%TEMP%\jaila_verify_clean_start"
if not exist "%TMP_DIR%" mkdir "%TMP_DIR%"

set "INDEX_FILE=%TMP_DIR%\index.html"
set "CSS_FILE=%TMP_DIR%\styles.css"
set "JS_FILE=%TMP_DIR%\app.js"
set "HEALTH_FILE=%TMP_DIR%\health.json"

echo [1/5] Henter index...
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing '%BASE_URL%/index.html').Content | Set-Content -Encoding UTF8 '%INDEX_FILE%'; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :failed

echo [2/5] Henter css...
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing '%BASE_URL%/css/styles.css').Content | Set-Content -Encoding UTF8 '%CSS_FILE%'; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :failed

echo [3/5] Henter js...
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing '%BASE_URL%/js/app.js').Content | Set-Content -Encoding UTF8 '%JS_FILE%'; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :failed

echo [4/5] Henter backend health...
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing '%HEALTH_URL%').Content | Set-Content -Encoding UTF8 '%HEALTH_FILE%'; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
if errorlevel 1 goto :failed

echo [5/5] Verificerer forventede markoerer...

set "HAS_CONTEXT_TITLE=0"
set "HAS_CONTEXT_PANEL=0"
set "HAS_CONTEXT_IMPORT=0"
set "HAS_HEALTH_STATUS=0"

findstr /C:"Upload kontekst til chat" "%INDEX_FILE%" >nul && set "HAS_CONTEXT_TITLE=1"
findstr /C:".chat-context-panel" "%CSS_FILE%" >nul && set "HAS_CONTEXT_PANEL=1"
findstr /C:"./api/contextApi.js" "%JS_FILE%" >nul && set "HAS_CONTEXT_IMPORT=1"
findstr /C:"status" "%HEALTH_FILE%" >nul && set "HAS_HEALTH_STATUS=1"

echo.
echo Resultat:
if "%HAS_CONTEXT_TITLE%"=="1" (echo  [OK] index indeholder "Upload kontekst til chat") else (echo  [FEJL] index mangler "Upload kontekst til chat")
if "%HAS_CONTEXT_PANEL%"=="1" (echo  [OK] css indeholder ".chat-context-panel") else (echo  [FEJL] css mangler ".chat-context-panel")
if "%HAS_CONTEXT_IMPORT%"=="1" (echo  [OK] js indeholder import af contextApi) else (echo  [FEJL] js mangler import af contextApi)
if "%HAS_HEALTH_STATUS%"=="1" (echo  [OK] backend health svarer) else (echo  [FEJL] backend health svar mangler status)

if "%HAS_CONTEXT_TITLE%"=="1" if "%HAS_CONTEXT_PANEL%"=="1" if "%HAS_CONTEXT_IMPORT%"=="1" if "%HAS_HEALTH_STATUS%"=="1" goto :success
goto :failed_markers

:success
echo.
echo ✅ Verifikation lykkedes. Frontend deployment ser korrekt ud.
echo.
goto :done

:failed_markers
echo.
echo ❌ Verifikation fejlede paa en eller flere markoerer.
echo    Koer DEPLOY_CLEAN_START.bat igen og verifikationen bagefter.
echo.
goto :done

:failed
echo.
echo ❌ Kunne ikke hente en eller flere URL'er.
echo    Tjek netvaerk, DNS, certifikat eller nginx routing.
echo.

:done
endlocal
pause
