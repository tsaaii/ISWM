# -*- mode: python ; coding: utf-8 -*-
# Build on Windows:  pyinstaller ISWM.spec   ->  dist/ISWM/ISWM.exe
# One-folder build (like adex_lite's SAC_monitor_*.spec): starts faster than
# one-file and keeps antivirus false positives down.

a = Analysis(
    ['run_iswm.py'],
    pathex=[],
    binaries=[],
    datas=[('web', 'web')],
    hiddenimports=['serial', 'serial.tools.list_ports', 'serial.urlhandler.protocol_socket',
                   'google.oauth2.service_account', 'google.auth.transport.requests', 'webview.platforms.edgechromium',
                   'webview.platforms.winforms', 'clr_loader'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pandas', 'tkinter', 'cv2.aruco', 'cv2.face', 'cv2.tracking', 'pytest'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ISWM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon='assets/iswm.ico',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ISWM')
