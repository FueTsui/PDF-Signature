# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['pdf-signature.py'],
    pathex=[],
    binaries=[],
    datas=[('signature.png', '.')],
    hiddenimports=['PIL._tkinter_finder', 'PIL.ImageTk', 'PyPDF2', 'reportlab.pdfgen', 'reportlab.lib.pagesizes', 'fitz', 'pymupdf'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [('O', None, 'OPTION'), ('O', None, 'OPTION')],
    name='PDF签名工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=True,
    icon=['signature.png'],
)
