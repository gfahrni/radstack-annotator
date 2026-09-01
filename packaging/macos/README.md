# Packaging macOS — RadStack Annotator portable onedir

## Build local (pour tester ici)
```bash
pip install . pyinstaller
# optionnel: ffmpeg pour Save Video (sinon Save Images seul marche)
# brew install ffmpeg
# cp $(which ffmpeg) packaging/macos/ffmpeg  # pour l'embarquer

pyinstaller packaging/macos/RadStack.spec --noconfirm
./dist/RadStackAnnotator/RadStackAnnotator
# ou
open dist/RadStackAnnotator/RadStackAnnotator
```

## Build via GitHub Actions
Push tag `v*` → workflow `build-macos.yml` (macos-latest) build et publie `RadStackAnnotator-portable-macos.zip` en Release à côté du zip Windows.
