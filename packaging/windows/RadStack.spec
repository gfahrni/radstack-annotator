# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for RadStack Annotator — Windows portable onedir
Build: pyinstaller packaging/windows/RadStack.spec
Output: dist/RadStackAnnotator/ (onedir) -> zipped as RadStackAnnotator-portable-windows.zip
"""
import os

block_cipher = None

# ffmpeg.exe is expected next to the spec at build time (downloaded by CI).
# If missing locally, build still succeeds but video export will require system ffmpeg.
ffmpeg_bin = os.path.join(os.path.dirname(__file__), 'ffmpeg.exe')
extra_binaries = []
if os.path.isfile(ffmpeg_bin):
    extra_binaries.append((ffmpeg_bin, '.'))

a = Analysis(
    ['../../run.py'],
    pathex=[os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))],
    binaries=extra_binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RadStackAnnotator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(os.path.dirname(__file__), 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='RadStackAnnotator',
)
