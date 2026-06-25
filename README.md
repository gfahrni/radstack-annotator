<p align="center">
  <img src="screenshots/screenshot_app.png" alt="RadStack Annotator screenshot" width="700">
</p>

# RadStack Annotator

A PyQt6-based GUI to browse, annotate, and export stacks of radiology images slice by slice. Supports arrow, rectangle, oval, and text annotations with an interpolation "stamp" feature across slices.

The goal is to produce an MP4 video of the annotated stack that can be embedded in PowerPoint, giving viewers near-scrollable dynamic images with visible annotations — something no current tool offers for radiology presentations.

![Python](https://img.shields.io/badge/python-%3E%3D3.8-blue)
![License](https://img.shields.io/badge/license-MIT-green)

<p align="center">
  <img src="screenshots/example.gif" alt="Demo" width="700">
</p>

---

## Features

- **Input format** — accepts `.jpg` / `.jpeg` / `.png` images sorted alphabetically (name them `001.jpg`, `002.jpg`, … for correct slice order)
- **Drag & drop** — drag a folder directly onto the app window to open it instantly
- **Auto brightness/contrast** — each slice is scaled to its own min/max pixel range
- **Annotation tools** — Arrow, Rectangle, Oval, and Text labels
- **Annotation editing** — select any annotation to move, resize, or recolor it; text boxes support editable content, font size, and optional background
- **Stamp & interpolate** — draw an annotation on one slice, scroll to another slice, and stamp it there; the app automatically interpolates the annotation across all intermediate slices
- **Color palette** — eight preset colors selectable per annotation
- **Slice navigation** — mouse wheel, vertical slider, or arrow keys
- **Export images** — save the annotated stack as a new folder of images
- **Export video** — compile the annotated stack into an MP4 optimised for smooth scrubbing in PowerPoint (keyframe every frame)
- **Preferences** — configurable background color and JPEG export quality

---

## Project structure

```
radstack-annotator/
├── run.py              # Entry point — handles CLI args, launches viewer
├── pyproject.toml      # Project metadata & dependencies
├── LICENSE             # MIT license
├── .gitignore
├── screenshots/        # Screenshots for the README
├── images/             # Default image folder (place your JPGs here)
├── images_annotated/   # Output folder created on export
└── src/
    ├── __init__.py     # Makes src/ a Python package
    ├── annotations.py  # Annotation data model and PIL rendering
    ├── loader.py       # load_images() — discovers and reads image files
    ├── saver.py        # Save/export logic for annotated stacks
    └── viewer.py       # ImageStackViewer class — UI layout & interaction
```

---

## Installation

### 1. Clone or download the repository

```bash
git clone https://github.com/yourusername/radstack-annotator.git
cd radstack-annotator
```

### 2. Install dependencies

Using **pip** (recommended):

```bash
pip install .
```

Or install manually:

```bash
pip install numpy PyQt6 Pillow
```

> **Video export** requires `ffmpeg` installed and available on your `PATH`.
> On macOS: `brew install ffmpeg`. On Linux: `sudo apt install ffmpeg`.
> On Windows: download from https://ffmpeg.org/.

---

## Usage

### Opening a folder

Three ways to open an image folder:

| Method | How |
|---|---|
| **Drag & drop** | Drag any folder onto the app window |
| **Open Folder button** | Click the button in the toolbar |
| **Command line** | `python run.py /path/to/images` |

Running without arguments opens the default `./images/` folder.

```bash
python run.py                    # opens ./images/ folder
python run.py /path/to/images    # opens a custom folder
```

Images are loaded in alphabetical order — name them `001.jpg`, `002.jpg`, … to guarantee correct slice ordering.

> **⚠️ Privacy warning:** Converting DICOM to JPG strips most metadata (name, ID, etc.), which is a first step toward anonymisation. However, it is your responsibility to ensure no text or other identifying information remains visible on the image pixels themselves.

---

## Controls

### Navigation

| Input | Action |
|---|---|
| Mouse wheel | Previous / next slice |
| ↑ / ↓ arrow keys | Previous / next slice |
| Vertical slider | Drag to jump to any slice |

### Annotation tools

Select a tool from the toolbar, then click and drag on the image to draw.

| Tool | Shape |
|---|---|
| → Arrow | Directed arrow |
| □ Rectangle | Bounding rectangle |
| ○ Oval | Ellipse |
| [T] Text | Text label with optional background |

After drawing, the tool is automatically deselected and the new annotation is selected.

### Editing annotations

| Input | Action |
|---|---|
| Click annotation | Select it |
| Drag body | Move the annotation |
| Drag corner handle | Resize the annotation |
| Click a palette color | Change color of selected annotation |
| Delete / Backspace | Delete selected annotation (and its stamped pair if linked) |
| Click empty area | Deselect |

### Text boxes

When drawing a text box, a dialog appears with:
- **Text field** — type the label content
- **Font size** — adjust with the spinner or slider (6–72 pt)
- **Background toggle** — show or hide the semi-transparent black background behind the text

### Stamp & interpolate

1. Draw an annotation on slice A — it stays selected.
2. Scroll (wheel, arrow keys, or slider) to a different slice B.
3. The app enters **stamp mode** automatically (shown in the title bar).
4. Click where you want the annotation to appear on slice B.
5. The annotation is stamped at that position and **automatically interpolated** across all slices between A and B.

Interpolated annotations can be selected and moved/resized like any other annotation — the change applies to both anchor slices simultaneously, keeping the interpolation consistent.

---

## Color palette

| Swatch | Hex | Color |
|---|---|---|
| ● | `#00e5ff` | Cyan (default) |
| ● | `#ffee58` | Yellow |
| ● | `#ff9100` | Orange |
| ● | `#ff4081` | Pink |
| ● | `#76ff03` | Lime |
| ● | `#e040fb` | Magenta |
| ● | `#ffffff` | White |
| ● | `#ff1744` | Red |

The first color (cyan) is selected by default when a new annotation is created.

---

## Export

| Action | Output location |
|---|---|
| **Save Images** | `{your-folder}_annotated/` next to your image folder |
| **Save Video** | `annotated-video.mp4` next to your image folder |

The video is encoded with H.264 at CRF 18 with a keyframe on every frame, making it suitable for frame-by-frame scrubbing in PowerPoint.

---

## Preferences

Open via **File → Preferences** (`Ctrl+,`):

| Setting | Description |
|---|---|
| Background color | Viewer background (default `#2b2b2b`) |
| Save format | `jpeg` or `png` for exported images |
| JPEG quality | 1–100 (default 100) |

Preferences are saved between sessions.

---

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open folder |
| `Ctrl+S` | Save annotated images |
| `Ctrl+,` | Preferences |
| `Ctrl+Q` | Quit |
| `↑` / `↓` | Navigate slices |
| `Delete` / `Backspace` | Delete selected annotation |

---

## Contributing

Contributions are welcome! Open an issue or submit a pull request.

---

## License

This project is open source and available under the [MIT License](https://opensource.org/licenses/MIT).
