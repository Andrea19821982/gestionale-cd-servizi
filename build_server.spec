# -*- mode: python ; coding: utf-8 -*-
# Costruisce dist/CalendarioTurni-Server/ come CARTELLA (onedir), non più un
# unico file .exe: un onefile riestrae tutto in una cartella temporanea a
# OGNI avvio, il che lo rende lento a partire (qualche secondo in più ogni
# volta). L'onedir estrae una sola volta in fase di build e poi si avvia
# quasi subito. Il database viene creato accanto all'eseguibile al primo
# avvio (vedi app/paths.py). L'intera cartella dist/CalendarioTurni-Server/
# va copiata/installata insieme (vedi installa_server.ps1), non il solo .exe.
#
# Uso: pyinstaller build_server.spec

a = Analysis(
    ['server_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'passlib.handlers.bcrypt',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CalendarioTurni-Server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='CalendarioTurni-Server',
)
