# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for RadStack Annotator — Windows portable onedir
Build: pyinstaller packaging/windows/RadStack.spec
Output: dist/RadStackAnnotator/ (onedir) -> zipped as RadStackAnnotator-portable-windows.zip
"""
import os

block_cipher = None

# PyInstaller defines SPECPATH (dir of .spec) and SPEC (path to .spec) at runtime.
# Fallback for local py_compile uses cwd.
try:
    _spec_dir = SPECPATH  # type: ignore
except NameError:
    try:
        _spec_dir = os.path.dirname(os.path.abspath(SPEC))  # type: ignore
    except NameError:
        _spec_dir = os.path.abspath(os.path.join(os.getcwd(), 'packaging/windows'))

# ffmpeg.exe is expected next to the spec at build time (downloaded by CI).
# If missing locally, build still succeeds but video export will require system ffmpeg.
ffmpeg_bin = os.path.join(_spec_dir, 'ffmpeg.exe')
extra_binaries = []
extra_datas = []
# Debug for CI
print(f"[spec] _spec_dir={_spec_dir} ffmpeg_bin={ffmpeg_bin} exists={os.path.isfile(ffmpeg_bin)} cwd={os.getcwd()} SPECPATH={globals().get('SPECPATH', 'N/A')}")
if os.path.isfile(ffmpeg_bin):
    extra_binaries.append((ffmpeg_bin, '.'))
    extra_datas.append((ffmpeg_bin, '.'))
    print(f"[spec] adding ffmpeg binary+data: {ffmpeg_bin}")
else:
    _alt = os.path.join(os.getcwd(), 'packaging/windows/ffmpeg.exe')
    print(f"[spec] fallback check {_alt} exists={os.path.isfile(_alt)}")
    if os.path.isfile(_alt):
        extra_binaries.append((_alt, '.'))
        extra_datas.append((_alt, '.'))
        print(f"[spec] adding fallback ffmpeg: {_alt}")
    else:
        print("[spec] WARNING: ffmpeg.exe not found, video export will require system ffmpeg")

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
