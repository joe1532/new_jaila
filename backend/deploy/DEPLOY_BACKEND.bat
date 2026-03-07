@echo off
setlocal

echo.
echo ========================================
echo   JAILA Backend Deployment
echo ========================================
echo.

set "SSH_KEY=C:\Users\micro\.ssh\id_ed25519"
set "SSH_USER=maestro"
set "SSH_HOST=168.119.63.168"
set "REMOTE_APP=/opt/jaila_backend"
set "REMOTE_TMP=~/jaila_backend_tmp"

set /p SUDO_PASS=Indtast sudo password for server: 

echo.
echo [1/7] Pakker backend filer lokalt...
if exist backend-deploy.zip del /f /q backend-deploy.zip
powershell -NoProfile -Command "Compress-Archive -Force -Path backend,requirements.txt -DestinationPath backend-deploy.zip"
if errorlevel 1 goto :local_failed

echo [2/7] Uploader archive og service-fil...
scp -i "%SSH_KEY%" backend-deploy.zip %SSH_USER%@%SSH_HOST%:~/backend-deploy.zip
if errorlevel 1 goto :upload_failed
scp -i "%SSH_KEY%" backend\deploy\jaila-backend.service %SSH_USER%@%SSH_HOST%:~/jaila-backend.service
if errorlevel 1 goto :upload_failed

echo [3/7] Opretter app mappe og udpakker...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S mkdir -p %REMOTE_APP% && rm -rf %REMOTE_TMP% && mkdir -p %REMOTE_TMP% && unzip -o ~/backend-deploy.zip -d %REMOTE_TMP%"
if errorlevel 1 goto :remote_failed

echo [4/7] Synkroniserer filer...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S rsync -a --delete %REMOTE_TMP%/ %REMOTE_APP%/ && echo %SUDO_PASS% | sudo -S chown -R www-data:www-data %REMOTE_APP%"
if errorlevel 1 goto :remote_failed

echo [5/7] Installerer Python dependencies i venv...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S -u www-data python3 -m venv %REMOTE_APP%/.venv && echo %SUDO_PASS% | sudo -S -u www-data %REMOTE_APP%/.venv/bin/pip install -r %REMOTE_APP%/requirements.txt"
if errorlevel 1 goto :remote_failed

echo [6/7] Installerer/opfrier systemd service...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S cp ~/jaila-backend.service /etc/systemd/system/jaila-backend.service && echo %SUDO_PASS% | sudo -S systemctl daemon-reload && echo %SUDO_PASS% | sudo -S systemctl enable jaila-backend && echo %SUDO_PASS% | sudo -S systemctl restart jaila-backend"
if errorlevel 1 goto :remote_failed

echo [7/7] Viser service-status...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S systemctl --no-pager --full status jaila-backend | head -n 20"
if errorlevel 1 goto :remote_failed

echo.
echo Deployment af backend lykkedes.
echo Husk: /etc/jaila-backend.env skal indeholde OPENAI_API_KEY og FRONTEND_ORIGINS.
echo.
goto :done

:local_failed
echo.
echo Local pakning fejlede.
echo.
goto :done

:upload_failed
echo.
echo Upload fejlede. Tjek SSH key/path og netvaerk.
echo.
goto :done

:remote_failed
echo.
echo Remote setup fejlede. Tjek sudo password, python3, unzip og rsync paa server.
echo.

:done
if exist backend-deploy.zip del /f /q backend-deploy.zip
endlocal
pause
