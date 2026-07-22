# Aggiorna il programma "Calendario Turni" a partire da un file .bundle
# preparato su un altro PC (vedi Guida_Aggiornamento_Calendario_Turni.docx).
#
# Uso: copia questo file, Aggiorna_Programma.bat e il file .bundle DENTRO
# la cartella del programma su questo PC, poi fai doppio clic su
# Aggiorna_Programma.bat. Non serve sapere nulla di Git: lo script fa
# tutto da solo e, prima di cambiare qualunque cosa, salva sempre una
# copia di sicurezza della cartella così com'è ora.

$cartella = $PSScriptRoot

function Scrivi($testo, $colore = "White") {
    Write-Host $testo -ForegroundColor $colore
}

Write-Host "============================================================"
Write-Host " Aggiornamento Calendario Turni"
Write-Host "============================================================"
Write-Host ""

# --- Trova il file .bundle nella stessa cartella (deve essere stato
#     copiato qui insieme a questo script) ---
$bundle = Get-ChildItem -Path $cartella -Filter "*.bundle" -File | Select-Object -First 1
if (-not $bundle) {
    Scrivi "ERRORE: non trovo nessun file .bundle in questa cartella." Red
    Scrivi "Copia anche il file .bundle qui dentro, insieme a questo script, poi riprova." Red
    Read-Host "Premi Invio per chiudere"
    exit 1
}
Scrivi "File di aggiornamento trovato: $($bundle.Name)" Cyan
Write-Host ""

# --- Git deve essere installato ---
try {
    git --version | Out-Null
} catch {
    Scrivi "ERRORE: su questo PC non risulta installato Git." Red
    Scrivi "Chiedi aiuto prima di procedere: serve per importare l'aggiornamento in sicurezza." Red
    Read-Host "Premi Invio per chiudere"
    exit 1
}

# --- Copia di sicurezza della cartella così com'è ora, PRIMA di ---
# --- toccare qualunque cosa (esclude solo cartelle rigenerabili) ---
$dataOra = Get-Date -Format "yyyy-MM-dd_HHmm"
$nomeCartella = Split-Path $cartella -Leaf
$cartellaBackup = Join-Path (Split-Path $cartella -Parent) "Backup_${nomeCartella}_$dataOra"

Scrivi "Creo una copia di sicurezza prima di procedere..." Yellow
Scrivi "  -> $cartellaBackup" Yellow
robocopy $cartella $cartellaBackup /MIR /XD .venv build dist __pycache__ .pytest_cache /XJ /NFL /NDL /NJH /NJS /NC /NS | Out-Null

if (-not (Test-Path $cartellaBackup)) {
    Scrivi "ERRORE: la copia di sicurezza non e' stata creata. Mi fermo qui per sicurezza, senza cambiare nulla." Red
    Read-Host "Premi Invio per chiudere"
    exit 1
}
Scrivi "Copia di sicurezza creata." Green
Write-Host ""

Set-Location $cartella
$eGiaRepositoryGit = Test-Path (Join-Path $cartella ".git")

if ($eGiaRepositoryGit) {
    Scrivi "Importo l'aggiornamento..." Cyan
    Write-Host ""
    & git pull $bundle.FullName master
    $riuscito = $LASTEXITCODE -eq 0
    Write-Host ""

    if ($riuscito) {
        Scrivi "============================================================" Green
        Scrivi " AGGIORNAMENTO RIUSCITO" Green
        Scrivi "============================================================" Green
        Scrivi "Riavvia il programma per vedere le novita'." Green
    } else {
        Scrivi "============================================================" Yellow
        Scrivi " C'E' STATO UN CONFLITTO" Yellow
        Scrivi "============================================================" Yellow
        Scrivi "Alcune modifiche si sovrappongono e serve una decisione umana." Yellow
        Scrivi "Non hai perso nulla: la copia di sicurezza e' qui:" Yellow
        Scrivi "  $cartellaBackup" Yellow
        Scrivi "Manda uno screenshot di questa finestra ad Andrea per farti aiutare." Yellow
    }
} else {
    Scrivi "Questa cartella non e' ancora collegata a Git." Cyan
    Scrivi "Preparo una cartella NUOVA con la versione aggiornata, senza toccare quella attuale." Cyan
    Write-Host ""
    $cartellaNuova = Join-Path (Split-Path $cartella -Parent) ("$nomeCartella-AGGIORNATO")

    & git clone $bundle.FullName $cartellaNuova 2>&1 | Out-Null

    if (-not (Test-Path $cartellaNuova)) {
        Scrivi "ERRORE: non sono riuscito a creare la cartella aggiornata. La cartella originale non e' stata toccata." Red
        Read-Host "Premi Invio per chiudere"
        exit 1
    }

    # Porta i dati/impostazioni esistenti (mai dentro al pacchetto di
    # aggiornamento) nella cartella nuova, cosi' e' gia' pronta all'uso.
    $fileDaPortare = @("turni.db", "secret_key.txt", "config.txt", "client_config.json")
    foreach ($f in $fileDaPortare) {
        $origine = Join-Path $cartella $f
        if (Test-Path $origine) { Copy-Item $origine (Join-Path $cartellaNuova $f) -Force }
    }
    foreach ($sottocartella in @("allegati", "backup")) {
        $origine = Join-Path $cartella $sottocartella
        if (Test-Path $origine) { Copy-Item $origine (Join-Path $cartellaNuova $sottocartella) -Recurse -Force }
    }

    Scrivi "============================================================" Green
    Scrivi " FATTO" Green
    Scrivi "============================================================" Green
    Scrivi "Ho preparato una cartella nuova, gia' aggiornata e con i tuoi dati:" Green
    Scrivi "  $cartellaNuova" Green
    Write-Host ""
    Scrivi "La cartella vecchia NON e' stata toccata." Yellow
    Scrivi "Prima di iniziare a usare quella nuova, fai controllare tutto ad Andrea." Yellow
}

Write-Host ""
Read-Host "Premi Invio per chiudere questa finestra"
