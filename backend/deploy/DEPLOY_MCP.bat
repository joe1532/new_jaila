@echo off
setlocal

echo.
echo ========================================
echo   JAILA MCP - Isoleret deployment
echo ========================================
echo.

cd /d "%~dp0\..\.."

if not defined SSH_KEY set "SSH_KEY=%USERPROFILE%\.ssh\id_ed25519"
set "SSH_USER=maestro"
set "SSH_HOST=168.119.63.168"
set "REMOTE_APP=/opt/jaila_mcp"
set "REMOTE_TMP=~/jaila_mcp_tmp"

if not defined SUDO_PASS set /p SUDO_PASS=Indtast sudo password for server:

echo [1/7] Pakker kun MCP-filer...
if exist jaila-mcp-deploy.tar.gz del /f /q jaila-mcp-deploy.tar.gz
tar -czf jaila-mcp-deploy.tar.gz ^
  backend\__init__.py ^
  backend\config.py ^
  backend\mcp_server.py ^
  backend\services\__init__.py ^
  backend\services\legal_search.py ^
  requirements-mcp.txt
if errorlevel 1 goto :local_failed

echo [2/7] Uploader MCP-pakke og driftsfiler...
scp -i "%SSH_KEY%" jaila-mcp-deploy.tar.gz %SSH_USER%@%SSH_HOST%:~/jaila-mcp-deploy.tar.gz
if errorlevel 1 goto :upload_failed
scp -i "%SSH_KEY%" backend\deploy\jaila-mcp.service %SSH_USER%@%SSH_HOST%:~/jaila-mcp.service
if errorlevel 1 goto :upload_failed
scp -i "%SSH_KEY%" backend\deploy\nginx-mcp-snippet.conf %SSH_USER%@%SSH_HOST%:~/nginx-mcp-snippet.conf
if errorlevel 1 goto :upload_failed
scp -i "%SSH_KEY%" backend\deploy\install-nginx-mcp.sh %SSH_USER%@%SSH_HOST%:~/install-nginx-mcp.sh
if errorlevel 1 goto :upload_failed

echo [3/7] Kontrollerer separat MCP-miljoefil...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S test -s /etc/jaila-mcp.env"
if errorlevel 1 (
  echo /etc/jaila-mcp.env mangler. Opret den med OPENAI_API_KEY og MCP_API_TOKEN.
  goto :remote_failed
)

echo [4/7] Udpakker til separat app-mappe...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S mkdir -p %REMOTE_APP% && rm -rf %REMOTE_TMP% && mkdir -p %REMOTE_TMP% && tar -xzf ~/jaila-mcp-deploy.tar.gz -C %REMOTE_TMP% && echo %SUDO_PASS% | sudo -S rsync -a --delete %REMOTE_TMP%/ %REMOTE_APP%/ && echo %SUDO_PASS% | sudo -S chown -R www-data:www-data %REMOTE_APP%"
if errorlevel 1 goto :remote_failed

echo [5/7] Opretter separat venv og installerer MCP-dependencies...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S -u www-data bash -lc 'set -e; cd %REMOTE_APP%; if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi; .venv/bin/pip install -r requirements-mcp.txt'"
if errorlevel 1 goto :remote_failed

echo [6/7] Installerer og genstarter kun MCP-servicen...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S cp ~/jaila-mcp.service /etc/systemd/system/jaila-mcp.service && echo %SUDO_PASS% | sudo -S systemctl daemon-reload && echo %SUDO_PASS% | sudo -S systemctl enable jaila-mcp && echo %SUDO_PASS% | sudo -S systemctl restart jaila-mcp"
if errorlevel 1 goto :remote_failed

echo [7/7] Kontrollerer MCP uden at beroere hoved-backenden...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S systemctl --no-pager --full status jaila-mcp | head -n 20 && curl -fsS --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8020/health"
if errorlevel 1 goto :remote_failed

echo.
echo MCP deployment lykkedes.
echo Nginx-eksempel er uploadet som ~/nginx-mcp-snippet.conf.
echo Aktiver separat med: sudo sh ~/install-nginx-mcp.sh
goto :done

:local_failed
echo Lokal pakning fejlede.
goto :done

:upload_failed
echo Upload fejlede. Tjek SSH-noegle og netvaerk.
goto :done

:remote_failed
echo MCP-setup fejlede. JAILA-hovedservicen er ikke genstartet.

:done
if exist jaila-mcp-deploy.tar.gz del /f /q jaila-mcp-deploy.tar.gz
endlocal
if not defined SKIP_PAUSE pause
