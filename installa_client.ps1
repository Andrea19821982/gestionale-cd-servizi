# Installa il client "Calendario Turni" sul PC di un collega: copia la
# cartella dist/CalendarioTurni (costruita con "pyinstaller build_client.spec")
# in una cartella personale del PC (nessun diritto di amministratore
# richiesto) e crea un collegamento sul Desktop con l'icona del programma.
#
# Uso: doppio clic su Installa_Client.bat (che richiama questo script).

$ErrorActionPreference = "Stop"

$cartellaOrigine = Join-Path $PSScriptRoot "dist\CalendarioTurni"
$cartellaDestinazione = Join-Path $env:LOCALAPPDATA "Programs\CalendarioTurni"
$nomeCollegamento = "Calendario Turni"

if (-not (Test-Path $cartellaOrigine)) {
    Write-Host "ERRORE: non trovo $cartellaOrigine" -ForegroundColor Red
    Write-Host "Genera prima l'eseguibile con: pyinstaller build_client.spec"
    exit 1
}

Write-Host "Installazione di Calendario Turni (client) in corso..."
Write-Host "Destinazione: $cartellaDestinazione"

New-Item -ItemType Directory -Force -Path $cartellaDestinazione | Out-Null
Copy-Item -Path (Join-Path $cartellaOrigine "*") -Destination $cartellaDestinazione -Recurse -Force

$eseguibile = Join-Path $cartellaDestinazione "CalendarioTurni.exe"

# --- Collegamento sul Desktop, con l'icona del programma ---
$percorsoDesktop = [Environment]::GetFolderPath("Desktop")
$percorsoCollegamento = Join-Path $percorsoDesktop "$nomeCollegamento.lnk"

$shell = New-Object -ComObject WScript.Shell
$collegamento = $shell.CreateShortcut($percorsoCollegamento)
$collegamento.TargetPath = $eseguibile
$collegamento.WorkingDirectory = $cartellaDestinazione
$collegamento.IconLocation = "$eseguibile,0"
$collegamento.Description = "Calendario Turni - CD Servizi"
$collegamento.Save()

Write-Host ""
Write-Host "Fatto! Trovi 'Calendario Turni' sul Desktop." -ForegroundColor Green
Write-Host "Al primo avvio ti verra' chiesto l'indirizzo del PC server (chiedilo"
Write-Host "a chi lo gestisce): resta salvato per le volte successive."
Write-Host ""
Read-Host "Premi Invio per chiudere"
