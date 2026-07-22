@echo off
REM Costruisce entrambe le cartelle di distribuzione (onedir, avvio rapido)
REM in dist\:
REM   CalendarioTurni-Server\  (da lasciare acceso su un PC dell'ufficio)
REM   CalendarioTurni\         (una per ogni PC che deve usare il programma)
REM
REM Dopo la build, usa Installa_Server.bat / Installa_Client.bat per
REM installarle con un collegamento sul Desktop, invece di copiarle a mano.
REM
REM Richiede le dipendenze di build installate: pip install -r requirements.txt

cd /d "%~dp0"

echo Costruzione del server...
.venv\Scripts\pyinstaller.exe build_server.spec --noconfirm
if errorlevel 1 goto errore

echo Costruzione del client...
.venv\Scripts\pyinstaller.exe build_client.spec --noconfirm
if errorlevel 1 goto errore

echo.
echo Fatto. Cartelle pronte in dist\CalendarioTurni-Server\ e dist\CalendarioTurni\
echo Ora esegui Installa_Server.bat (su questo PC, se fa da server) e/o
echo Installa_Client.bat per creare il collegamento sul Desktop.
pause
exit /b 0

:errore
echo.
echo Costruzione fallita: controlla i messaggi sopra.
pause
exit /b 1
