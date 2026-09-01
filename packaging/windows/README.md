# Packaging Windows — RadStack Annotator portable onedir

## Contenu
- `icon.ico` — icône de l'exe (multi-résolution 16-256)
- `RadStack.spec` — config PyInstaller onedir, windowed, embarque `ffmpeg.exe` si présent à côté du spec
- `ffmpeg.exe` — **non commité** (trop lourd). Téléchargé par la CI ou placé manuellement pour un build local.

## Build local sur Windows
```powershell
# 1. Installer deps
pip install . pyinstaller

# 2. Placer ffmpeg.exe à côté du spec (optionnel mais recommandé)
# curl -L https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip -o ffmpeg.zip
# Expand-Archive ffmpeg.zip -Force; Copy-Item ffmpeg\bin\ffmpeg.exe packaging\windows\ffmpeg.exe

# 3. Build
pyinstaller packaging/windows/RadStack.spec

# 4. Test
.\dist\RadStackAnnotator\RadStackAnnotator.exe  # ou drag & drop dossier images

# 5. Zip portable
Compress-Archive -Path dist\RadStackAnnotator -DestinationPath RadStackAnnotator-portable-windows.zip -Force
```

## Build via GitHub Actions
Push un tag `v*` → workflow `.github/workflows/build-windows.yml` build automatiquement et publie le zip en Release.
