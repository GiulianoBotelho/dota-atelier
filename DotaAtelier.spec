# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

safe_assets = [(str(p), str(Path('assets') / p.relative_to('assets').parent))
               for p in Path('assets').rglob('*') if p.is_file()
               and (p.suffix.lower() in {'.png', '.webp', '.jpg', '.jpeg'}
                    or p.name in {'catalog.json', 'skin-recipes.json'})
               and p.name != 'dota-logo.png']


a = Analysis(
    ['manager.py'],
    pathex=[],
    binaries=[],
    datas=safe_assets,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DotaAtelier',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DotaAtelier',
)
