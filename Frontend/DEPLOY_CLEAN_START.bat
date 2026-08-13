@echo off
setlocal

echo.
echo ========================================
echo   JAILA Clean-Start Deployment
echo ========================================
echo.

if not defined SSH_KEY set "SSH_KEY=%USERPROFILE%\.ssh\id_ed25519"
set "SSH_USER=maestro"
set "SSH_HOST=168.119.63.168"
set "REMOTE_BASE=/var/www/site/clean-start"

if not defined SUDO_PASS set /p SUDO_PASS=Indtast sudo password for server: 

echo.
echo [1/4] Uploader clean-start filer...
rem Staging ryddes foerst. Ellers lever gamle filer videre, og scp arver de rettigheder,
rem mapperne havde i forvejen - hvilket har sat webroot i staa en gang. Se trin 3b.
rem
rem chmod SKAL koere foer rm: er en mappe kommet over som dr-x------, mangler den write,
rem og saa kan indholdet ikke slettes - heller ikke af ejeren. Det er samme manglende bit,
rem der laa bag webroot-nedbruddet, blot her paa vejen ind i stedet for ud.
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "chmod -R u+rwX ~/clean-start-staging 2>/dev/null; rm -rf ~/clean-start-staging && mkdir -p ~/clean-start-staging"
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

echo [3b/4] Retter rettigheder saa nginx kan laese filerne...
rem scp bevarer rettigheder fra den maskine, filerne kom fra. Kom en mappe over som
rem dr-x------, kan www-data ikke gaa ind i den, og alt indeni svarer 404 - mens app.js
rem selv svarer 200. Resultatet er en side, der ser ud til at indlaese, men falder over
rem sin foerste import, saa end ikke login virker. Store X saetter kun x-bit paa mapper.
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S chmod -R u=rwX,go=rX %REMOTE_BASE%"
if errorlevel 1 goto :remote_failed

echo [4/4] Reloader nginx...
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "echo %SUDO_PASS% | sudo -S systemctl reload nginx"
if errorlevel 1 goto :remote_failed

echo [4b/4] Kontrollerer at undermapperne faktisk kan hentes...
rem En deploy, der lykkes uden at filerne kan hentes, er ikke lykkedes. Der hentes derfor
rem en fil fra en undermappe, ikke kun forsiden.
ssh -i "%SSH_KEY%" %SSH_USER%@%SSH_HOST% "curl -s -o /dev/null -w 'js/state/store.js: HTTP %%{http_code}\n' https://skat-chat.dk/clean-start/js/state/store.js"
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
if not defined SKIP_PAUSE pause
