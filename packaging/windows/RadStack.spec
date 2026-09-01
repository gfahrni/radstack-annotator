# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for RadStack Annotator — Windows portable onedir
Build: pyinstaller packaging/windows/RadStack.spec
Output: dist/RadStackAnnotator/ (onedir) -> zipped as RadStackAnnotator-portable-windows.zip
"""
import os

block_cipher = None

# In a .spec __file__ is not defined — use SPECPATH/SPEC which PyInstaller provides.
_spec_dir = globals().get('SPECPATH') or os.path.dirname(os.path.abspath(globals().get('SPEC', __file__) if '__file__' in globals() else os.path.join(os.getcwd(), 'packaging/windows/RadStack.spec')))
# Fallback: directory of this spec
try:
    _spec_dir = SPECPATH  # type: ignore # defined by PyInstaller
except NameError:
    try:
        _spec_dir = os.path.dirname(os.path.abspath(SPEC))  # type: ignore
    except NameError:
        _spec_dir = os.path.join(os.getcwd(), 'packaging/windows')

# ffmpeg.exe is expected next to the spec at build time (downloaded by CI).
# If missing locally, build still succeeds but video export will require system ffmpeg.
ffmpeg_bin = os.path.join(_spec_dir, 'ffmpeg.exe')
extra_binaries = []
if os.path.isfile(ffmpeg_bin):
    extra_binaries.append((ffmpeg_bin, '.'))

a = Analysis(
    ['../../run.py'],
    pathex=[os.path.abspath(os.path.join(_spec_dir, '../..'))],
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
    icon=os.path.join(_spec_dir, 'icon.ico'),
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
