# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for RadStack Annotator — macOS portable onedir
Build locally: pyinstaller packaging/macos/RadStack.spec
Output: dist/RadStackAnnotator/ (onedir) -> manual test or zip
"""
import os

block_cipher = None

try:
    _spec_dir = SPECPATH  # type: ignore
except NameError:
    try:
        _spec_dir = os.path.dirname(os.path.abspath(SPEC))  # type: ignore
    except NameError:
        _spec_dir = os.path.abspath(os.path.join(os.getcwd(), 'packaging/macos'))

# ffmpeg is optional on macOS: if present next to spec, bundle it.
# Otherwise user needs `brew install ffmpeg` for Save Video.
ffmpeg_bin = os.path.join(_spec_dir, 'ffmpeg')
ffmpeg_exe = os.path.join(_spec_dir, 'ffmpeg.exe')
extra_binaries = []
extra_datas = []
for cand in (ffmpeg_bin, ffmpeg_exe):
    if os.path.isfile(cand):
        extra_binaries.append((cand, '.'))
        extra_datas.append((cand, '.'))
        print(f"[spec] adding ffmpeg: {cand}")

icon_path = os.path.join(_spec_dir, 'icon.icns')
if not os.path.isfile(icon_path):
    # fallback to ico if icns missing
    icon_path = os.path.join(_spec_dir, 'icon.ico')
    if not os.path.isfile(icon_path):
        icon_path = os.path.join(os.path.dirname(_spec_dir), 'windows/icon.ico')

a = Analysis(
    ['../../run.py'],
    pathex=[os.path.abspath(os.path.join(_spec_dir, '../..'))] if os.path.isdir(os.path.join(_spec_dir, '../..')) else [os.getcwd()],
    binaries=extra_binaries,
    datas=extra_datas,
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.isfile(icon_path) else None,
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
