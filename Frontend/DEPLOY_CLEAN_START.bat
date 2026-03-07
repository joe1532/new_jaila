@echo off
setlocal

echo.
echo ========================================
echo   JAILA Clean-Start Deployment
echo ========================================
echo.

set "SSH_KEY=C:\Users\micro\.ssh\id_ed25519"
set "SSH_USER=maestro"
set "SSH_HOST=168.119.63.168"
set "REMOTE_BASE=/var/www/site/clean-start"

set /p SUDO_PASS=Indtast sudo password for server: 

echo.
echo [1/4] Uploader clean-start filer...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "mkdir -p ~/clean-start-staging"
if errorlevel 1 goto :upload_failed
scp -i "%SSH_KEY%" index.html %SSH_USER%@%SSH_HOST%:~/clean-start-staging/index.html
if errorlevel 1 goto :upload_failed
scp -i "%SSH_KEY%" REQUIREMENTS.md %SSH_USER%@%SSH_HOST%:~/clean-start-staging/REQUIREMENTS.md
if errorlevel 1 goto :upload_failed
scp -r -i "%SSH_KEY%" css %SSH_USER%@%SSH_HOST%:~/clean-start-staging/
if errorlevel 1 goto :upload_failed
scp -r -i "%SSH_KEY%" js %SSH_USER%@%SSH_HOST%:~/clean-start-staging/
if errorlevel 1 goto :upload_failed

echo [2/4] Opretter target mappe paa server...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S mkdir -p %REMOTE_BASE%/css %REMOTE_BASE%/js"
if errorlevel 1 goto :remote_failed

echo [3/4] Kopierer filer til webroot...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S rm -rf %REMOTE_BASE%/css %REMOTE_BASE%/js && echo %SUDO_PASS% | sudo -S mkdir -p %REMOTE_BASE%/css %REMOTE_BASE%/js && echo %SUDO_PASS% | sudo -S cp ~/clean-start-staging/index.html %REMOTE_BASE%/index.html && echo %SUDO_PASS% | sudo -S cp ~/clean-start-staging/index.html /var/www/site/index.html && echo %SUDO_PASS% | sudo -S cp ~/clean-start-staging/REQUIREMENTS.md %REMOTE_BASE%/REQUIREMENTS.md && echo %SUDO_PASS% | sudo -S cp -r ~/clean-start-staging/css/. %REMOTE_BASE%/css/ && echo %SUDO_PASS% | sudo -S cp -r ~/clean-start-staging/js/. %REMOTE_BASE%/js/"
if errorlevel 1 goto :remote_failed

echo [4/4] Reloader nginx...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S systemctl reload nginx"
if errorlevel 1 goto :remote_failed

echo.
echo ✅ Deployment lykkedes.
echo URL: https://skat-chat.dk/clean-start/index.html
echo.
goto :done

:upload_failed
echo.
echo ❌ Upload fejlede. Tjek SSH key/path og netvaerk.
echo.
goto :done

:remote_failed
echo.
echo ❌ Remote copy/reload fejlede. Tjek sudo password og server adgang.
echo.

:done
endlocal
pause
