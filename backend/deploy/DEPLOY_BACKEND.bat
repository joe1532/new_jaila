@echo off
setlocal

echo.
echo ========================================
echo   JAILA Backend Deployment
echo ========================================
echo.

if not defined SSH_KEY set "SSH_KEY=%USERPROFILE%\.ssh\id_ed25519"
set "SSH_USER=maestro"
set "SSH_HOST=168.119.63.168"
set "REMOTE_APP=/opt/jaila_backend"
set "REMOTE_TMP=~/jaila_backend_tmp"
set "REMOTE_DATA_DIR=/var/lib/jaila/analyse_logs"
set "REMOTE_CACHE_DIR=/var/lib/jaila/lovhistorik_cache"

if not defined SUDO_PASS set /p SUDO_PASS=Indtast sudo password for server: 

echo.
echo [1/7] Pakker backend filer lokalt...
if exist backend-deploy.tar.gz del /f /q backend-deploy.tar.gz
rem lovhistorik skal med: backend/services/forarbejder_service.py importerer motoren derfra.
rem .cache udelades bevidst - den fylder flere hundrede megabyte og bygges op paa serveren
rem i /var/lib/jaila/lovhistorik_cache, hvor den overlever naeste udrulning.
tar -czf backend-deploy.tar.gz --exclude=".cache" --exclude="__pycache__" backend requirements.txt lovhistorik
if errorlevel 1 goto :local_failed

echo [2/7] Uploader archive og service-fil...
scp -i "%SSH_KEY%" backend-deploy.tar.gz %SSH_USER%@%SSH_HOST%:~/backend-deploy.tar.gz
if errorlevel 1 goto :upload_failed
scp -i "%SSH_KEY%" backend\deploy\jaila-backend.service %SSH_USER%@%SSH_HOST%:~/jaila-backend.service
if errorlevel 1 goto :upload_failed

echo [3/7] Opretter app mappe og udpakker...
rem Projektmapperne ligger i OneDrive og baerer Windows' ReadOnly-attribut, som tar
rem oversaetter til dr-xr-xr-x. Uden write-bit kan tar ikke laegge filer i mappen, den
rem lige har oprettet, og udpakningen fejler fil for fil.
rem
rem --delay-directory-restore udpakker foerst indholdet og saetter foerst mappernes
rem rettigheder til sidst, saa udpakningen kan gennemfoeres. Derefter rettes de med
rem chmod. rsync -a bevarer rettigheder, saa det der landes i app-mappen skal vaere
rem laesbart for den bruger, servicen koerer som.
rem
rem chmod foer rm af samme grund: uden write-bit kan en mappes indhold ikke slettes,
rem heller ikke af ejeren.
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S mkdir -p %REMOTE_APP% && chmod -R u+rwX %REMOTE_TMP% 2>/dev/null; rm -rf %REMOTE_TMP% && mkdir -p %REMOTE_TMP% && tar -xzf ~/backend-deploy.tar.gz --delay-directory-restore -C %REMOTE_TMP% && chmod -R u=rwX,go=rX %REMOTE_TMP%"
if errorlevel 1 goto :remote_failed

echo [4/7] Synkroniserer filer...
rem .venv skal undtages. Miljoet ligger i app-mappen, men findes ikke i arkivet, saa
rem --delete fjernede det ved hver udrulning. Alle pakker blev derfor hentet forfra hver
rem gang - omkring et minut og 579 MB - og hash-tjekket i trin 5, der skulle springe pip
rem over ved uaendrede requirements, kunne aldrig traede i kraft.
rem
rem Skal miljoet bygges rent, slettes det manuelt:
rem   sudo rm -rf /opt/jaila_backend/.venv
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S rsync -a --delete --exclude='.venv' %REMOTE_TMP%/ %REMOTE_APP%/ && echo %SUDO_PASS% | sudo -S chown -R www-data:www-data %REMOTE_APP%"
if errorlevel 1 goto :remote_failed

echo [4b/7] Sikrer persistente datamapper for analyse-logs og forarbejdscache...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S mkdir -p %REMOTE_DATA_DIR% %REMOTE_CACHE_DIR% && echo %SUDO_PASS% | sudo -S chown -R www-data:www-data /var/lib/jaila"
if errorlevel 1 goto :remote_failed

echo [5/7] Sikrer venv og installerer kun dependencies ved behov...
rem Hashen skaeres med cut -c1-64, ikke med bash-udtrykket ${VAR%% *}. Et dobbelt
rem procenttegn bliver til ét, naar .bat-filen koerer, saa bash fik ${VAR% *} - korteste
rem match i stedet for laengste. Hashen beholdt derfor et mellemrum til sidst, mens
rem filen blev skrevet uden, og de to kunne aldrig vaere ens. pip koerte ved hver
rem udrulning, ogsaa naar intet var aendret. En sha256 er altid 64 tegn.
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S -u www-data bash -lc 'set -e; APP=%REMOTE_APP%; VENV=$APP/.venv; REQ=$APP/requirements.txt; HASH_FILE=/var/lib/jaila/requirements.sha256; if [ ! -d $VENV ]; then python3 -m venv $VENV; fi; NEW_HASH=$(sha256sum $REQ | cut -c1-64); OLD_HASH=\"\"; if [ -f $HASH_FILE ]; then OLD_HASH=$(cat $HASH_FILE); fi; if [ ! -x $VENV/bin/pip ] || [ \"$NEW_HASH\" != \"$OLD_HASH\" ]; then $VENV/bin/pip install -r $REQ; echo $NEW_HASH > $HASH_FILE; echo Dependencies opdateret.; else echo Requirements uændret - springer pip install over.; fi'"
if errorlevel 1 goto :remote_failed

echo [6/7] Installerer/opfrier systemd service...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S cp ~/jaila-backend.service /etc/systemd/system/jaila-backend.service && echo %SUDO_PASS% | sudo -S systemctl daemon-reload && echo %SUDO_PASS% | sudo -S systemctl enable jaila-backend && echo %SUDO_PASS% | sudo -S systemctl restart jaila-backend"
if errorlevel 1 goto :remote_failed

echo [7/7] Viser service-status...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S systemctl --no-pager --full status jaila-backend | head -n 20"
if errorlevel 1 goto :remote_failed

echo [7b/7] Kontrollerer at API'et svarer efter genstart...
rem En service, der er "active", kan stadig have fejlet under import. Der spoerges derfor
rem paa et endepunkt frem for at stole paa status. Servicen faar et oejeblik til at binde.
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "sleep 4; curl -s -o /dev/null -w 'api/health: HTTP %%{http_code}\n' http://127.0.0.1:8010/api/health; curl -s -w '\n' http://127.0.0.1:8010/api/forarbejder/laws | head -c 200; echo"
if errorlevel 1 goto :remote_failed

echo.
echo Deployment af backend lykkedes.
echo Husk: /etc/jaila-backend.env skal indeholde OPENAI_API_KEY og FRONTEND_ORIGINS.
echo Forarbejder-fanen kraever desuden linjen:
echo   LOVHISTORIK_CACHE_DIR=%REMOTE_CACHE_DIR%
echo Uden den lander cachen i app-mappen og slettes ved naeste udrulning.
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
if exist backend-deploy.tar.gz del /f /q backend-deploy.tar.gz
endlocal
if not defined SKIP_PAUSE pause
