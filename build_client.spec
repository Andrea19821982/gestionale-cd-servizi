# -*- mode: python ; coding: utf-8 -*-
# Costruisce dist/CalendarioTurni/ come CARTELLA (onedir), non più un unico
# file .exe: vedi la stessa nota in build_server.spec sul perché onedir parte
# più in fretta di onefile. Il client punta all'indirizzo del server (chiesto
# al primo avvio, salvato in client_config.json accanto all'eseguibile).
# L'intera cartella dist/CalendarioTurni/ va copiata/installata insieme
# (vedi installa_client.ps1), non il solo .exe.
#
# Uso: pyinstaller build_client.spec

a = Analysis(
    ['client_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'clr_loader',
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
    name='CalendarioTurni',
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
    name='CalendarioTurni',
)
