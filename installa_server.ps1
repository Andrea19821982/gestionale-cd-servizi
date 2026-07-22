# Installa "Calendario Turni - Server" sul PC che deve fare da server:
# copia la cartella dist/CalendarioTurni-Server (costruita con
# "pyinstaller build_server.spec") in una cartella personale del PC (nessun
# diritto di amministratore richiesto) e crea un collegamento sul Desktop
# con l'icona del programma.
#
# Uso: doppio clic su Installa_Server.bat (che richiama questo script).

$ErrorActionPreference = "Stop"

$cartellaOrigine = Join-Path $PSScriptRoot "dist\CalendarioTurni-Server"
$cartellaDestinazione = Join-Path $env:LOCALAPPDATA "Programs\CalendarioTurni-Server"
$nomeCollegamento = "Calendario Turni - Server"

if (-not (Test-Path $cartellaOrigine)) {
    Write-Host "ERRORE: non trovo $cartellaOrigine" -ForegroundColor Red
    Write-Host "Genera prima l'eseguibile con: pyinstaller build_server.spec"
    exit 1
}

Write-Host "Installazione di Calendario Turni (server) in corso..."
Write-Host "Destinazione: $cartellaDestinazione"

New-Item -ItemType Directory -Force -Path $cartellaDestinazione | Out-Null
Copy-Item -Path (Join-Path $cartellaOrigine "*") -Destination $cartellaDestinazione -Recurse -Force

$eseguibile = Join-Path $cartellaDestinazione "CalendarioTurni-Server.exe"

# --- Collegamento sul Desktop, con l'icona del programma ---
$percorsoDesktop = [Environment]::GetFolderPath("Desktop")
$percorsoCollegamento = Join-Path $percorsoDesktop "$nomeCollegamento.lnk"

$shell = New-Object -ComObject WScript.Shell
$collegamento = $shell.CreateShortcut($percorsoCollegamento)
$collegamento.TargetPath = $eseguibile
$collegamento.WorkingDirectory = $cartellaDestinazione
$collegamento.IconLocation = "$eseguibile,0"
$collegamento.Description = "Calendario Turni - Server (CD Servizi)"
$collegamento.Save()

Write-Host ""
Write-Host "Fatto! Trovi 'Calendario Turni - Server' sul Desktop." -ForegroundColor Green
Write-Host "Avvialo e lascialo acceso durante l'orario di lavoro: l'indirizzo"
Write-Host "da dare ai colleghi comparira' nell'icona vicino all'orologio e"
Write-Host "in un avviso, oltre a essere scritto nel file 'indirizzo_server.txt'"
Write-Host "dentro $cartellaDestinazione."
Write-Host ""
Write-Host "Suggerimento: se vuoi che si avvii da solo ogni volta che accendi"
Write-Host "questo PC, premi Win+R, scrivi 'shell:startup' e trascina li'"
Write-Host "dentro una copia del collegamento appena creato sul Desktop."
Write-Host ""
Read-Host "Premi Invio per chiudere"
