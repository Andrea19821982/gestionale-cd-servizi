@echo off
REM Costruisce il file di installazione da consegnare ai colleghi:
REM   installer\Gestionale-CD-Servizi-Setup-<versione>.exe
REM
REM Ricostruisce prima i due eseguibili, poi li impacchetta con Inno Setup.
REM L'ordine conta: compilare l'installer senza rifare la build vorrebbe dire
REM spedire la versione precedente del programma senza accorgersene.
REM
REM Richiede:
REM   - le dipendenze di build: pip install -r requirements.txt
REM   - Inno Setup 6: winget install JRSoftware.InnoSetup

cd /d "%~dp0"

REM Inno Setup si installa per utente o per tutti, a seconda di come e' stato
REM messo: cerchiamo nei due posti invece di dare per scontato uno dei due.
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" goto manca_inno

echo [1/3] Costruzione del server...
.venv\Scripts\pyinstaller.exe build_server.spec --noconfirm --clean
if errorlevel 1 goto errore

echo.
echo [2/3] Costruzione del client...
.venv\Scripts\pyinstaller.exe build_client.spec --noconfirm --clean
if errorlevel 1 goto errore

echo.
echo [3/3] Creazione del file di installazione...
"%ISCC%" installer.iss
if errorlevel 1 goto errore

echo.
echo ============================================================
echo  FATTO
echo ============================================================
echo Il file di installazione e' nella cartella "installer".
echo Mandalo ai colleghi: basta un doppio clic, e durante
echo l'installazione si scegli se installare il Client (sui PC di
echo tutti) o il Server (su un solo PC, quello che tiene i dati).
pause
exit /b 0

:manca_inno
echo.
echo ERRORE: Inno Setup 6 non risulta installato su questo PC.
echo Serve per creare il file di installazione. Installalo con:
echo.
echo     winget install JRSoftware.InnoSetup
echo.
pause
exit /b 1

:errore
echo.
echo Costruzione fallita: controlla i messaggi sopra.
pause
exit /b 1
