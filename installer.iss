; Installer di "Gestionale CD-Servizi" (Inno Setup 6).
;
; Produce un unico file Setup da mandare ai colleghi: procedura guidata in
; italiano, scelta fra Client e Server, collegamenti nel menu Start e sul
; Desktop, voce in "App e funzionalità" con disinstallazione. Sostituisce gli
; script Installa_Client.bat / Installa_Server.bat, che chiedevano di
; riconoscere il file giusto e non lasciavano modo di disinstallare.
;
; Per compilarlo: costruisci_installer.bat (che ricostruisce prima gli
; eseguibili, altrimenti si impacchetta una versione vecchia).
;
; Due scelte importanti, spiegate perché non sono ovvie rileggendo il file:
;
; 1) PrivilegesRequired=lowest — installazione per utente in
;    %LOCALAPPDATA%\Programs, senza password di amministratore. I colleghi
;    possono installarlo da soli, e gli aggiornamenti non richiedono di
;    chiamare qualcuno con i diritti. È lo stesso approccio di Chrome e
;    Visual Studio Code.
;
; 2) La disinstallazione NON cancella i dati (database, allegati, backup):
;    stanno in %LOCALAPPDATA%\CD-Servizi, fuori da questa cartella, e non
;    vengono toccati di proposito. Non c'è nemmeno la domanda "vuoi
;    rimuovere anche i dati?": su un archivio di turni che esiste in una
;    sola copia, un clic distratto costerebbe troppo. Chi deve fare pulizia
;    davvero cancella quella cartella a mano.

#define NomeApp "Gestionale CD-Servizi"
; Versione: tenerla allineata a versione_client.txt e versione_server.txt,
; che sono le informazioni incorporate nei due eseguibili.
#define Versione "1.0.3"
#define Produttore "CD Servizi"

[Setup]
; AppId identifica il programma per Windows: è la chiave con cui un nuovo
; Setup riconosce di essere un aggiornamento invece di una seconda
; installazione affiancata. Non va mai cambiato.
AppId={{E0E3454A-E3C5-4465-9FB3-5B97E0CE4678}
AppName={#NomeApp}
AppVersion={#Versione}
AppVerName={#NomeApp} {#Versione}
AppPublisher={#Produttore}
VersionInfoVersion={#Versione}
VersionInfoCompany={#Produttore}
VersionInfoDescription=Installazione di {#NomeApp}

DefaultDirName={autopf}\{#NomeApp}
DefaultGroupName={#NomeApp}
; Il gruppo nel menu Start è sempre lo stesso: una pagina in meno da leggere
; per chi installa, e nessun modo di sbagliarla.
DisableProgramGroupPage=yes
AllowNoIcons=yes

PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
MinVersion=10.0

; Se il server è acceso, il suo .exe è in uso e non si può sovrascrivere:
; Inno lo rileva e propone di chiuderlo, invece di fallire a metà
; installazione lasciando la cartella in uno stato incoerente.
CloseApplications=yes
RestartApplications=no
SetupMutex=GestionaleCDServiziSetup

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\icon.ico
; L'icona mostrata in "App e funzionalità": punta al file .ico installato
; sotto, non a un eseguibile, perché quale dei due .exe c'è dipende dai
; componenti scelti.
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#NomeApp}

OutputDir=installer
OutputBaseFilename=Gestionale-CD-Servizi-Setup-{#Versione}

[Languages]
Name: "italiano"; MessagesFile: "compiler:Languages\Italian.isl"

[Types]
Name: "client"; Description: "Client — per i PC dei colleghi"
Name: "server"; Description: "Server — solo per il PC che fa da server"
Name: "completa"; Description: "Completa — client e server su questo PC"
Name: "personalizzata"; Description: "Personalizzata"; Flags: iscustom

[Components]
Name: "client"; Description: "Calendario Turni (client): per consultare e modificare i turni"; Types: client completa
Name: "server"; Description: "Calendario Turni — Server: da installare su un solo PC, quello che tiene i dati"; Types: server completa

[Files]
; Excludes è una precauzione, non una necessità: PyInstaller ricrea dist\ da
; zero ad ogni build, quindi in teoria lì dentro non c'è nulla di tutto
; questo. Ma se qualcuno prova il server avviandolo dalla cartella dist, il
; database vero finisce accanto all'eseguibile — e da lì, senza questa
; riga, finirebbe dentro al Setup e sui PC di tutti i colleghi, che al primo
; avvio lo recupererebbero come se fosse il loro (vedi app/paths.py).
Source: "dist\CalendarioTurni\*"; DestDir: "{app}\Client"; \
    Excludes: "turni.db,turni.db-wal,turni.db-shm,secret_key.txt,log.txt,indirizzo_server.txt,client_config.json,.dati_migrati,backup\*,allegati\*"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; Components: client
Source: "dist\CalendarioTurni-Server\*"; DestDir: "{app}\Server"; \
    Excludes: "turni.db,turni.db-wal,turni.db-shm,secret_key.txt,log.txt,indirizzo_server.txt,client_config.json,.dati_migrati,backup\*,allegati\*"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; Components: server
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Tasks]
Name: "iconadesktop"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "avvioautomatico"; Description: "Avvia il server automaticamente all'accensione del PC"; \
    GroupDescription: "Opzioni del server:"; Components: server; Flags: unchecked

[Icons]
Name: "{group}\Calendario Turni"; Filename: "{app}\Client\CalendarioTurni.exe"; Components: client
Name: "{group}\Calendario Turni - Server"; Filename: "{app}\Server\CalendarioTurni-Server.exe"; Components: server
Name: "{group}\Disinstalla {#NomeApp}"; Filename: "{uninstallexe}"

; Gli stessi nomi che usavano installa_client.ps1 / installa_server.ps1: su
; un PC che aveva la versione vecchia, i collegamenti sul Desktop vengono
; così sostituiti invece di raddoppiarsi, e nessuno resta a lanciare per
; sbaglio il programma della vecchia cartella.
Name: "{autodesktop}\Calendario Turni"; Filename: "{app}\Client\CalendarioTurni.exe"; \
    Tasks: iconadesktop; Components: client
Name: "{autodesktop}\Calendario Turni - Server"; Filename: "{app}\Server\CalendarioTurni-Server.exe"; \
    Tasks: iconadesktop; Components: server

Name: "{userstartup}\Calendario Turni - Server"; Filename: "{app}\Server\CalendarioTurni-Server.exe"; \
    Tasks: avvioautomatico; Components: server

[Run]
Filename: "{app}\Server\CalendarioTurni-Server.exe"; Description: "Avvia ora il server"; \
    Flags: nowait postinstall skipifsilent; Components: server
Filename: "{app}\Client\CalendarioTurni.exe"; Description: "Apri Calendario Turni"; \
    Flags: nowait postinstall skipifsilent; Components: client
