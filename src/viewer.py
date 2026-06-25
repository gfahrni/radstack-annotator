"""
RadStack Annotator — graphical window to browse a folder of images
slice by slice, with annotation tools and stamp interpolation.

This module contains the ImageStackViewer class, which builds a
matplotlib GUI to let a user:
    - Scroll through slices (mouse wheel, slider).
    - Draw arrow, rectangle, oval, or text label annotations (click-drag on the image).
    - Select / move / reshape annotations.
    - Stamp an annotation on another slice (scroll → click → interpolate all slices between).
    - Save the annotated stack.
"""

import json
import os
import math
import subprocess
import tempfile
import shutil
import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog

import numpy as np
from PIL import Image as PILImage
import matplotlib

matplotlib.use('TkAgg')

matplotlib.rcParams['figure.dpi'] = 120

matplotlib.rcParams['keymap.quit'] = [
    k for k in matplotlib.rcParams.get('keymap.quit', [])
    if k.lower() != 'q'
]
import matplotlib.pyplot as plt
from matplotlib.backend_bases import cursors
from matplotlib.widgets import Slider
from matplotlib.patches import FancyArrowPatch, Rectangle as MplRect, Ellipse, Circle
from matplotlib.lines import Line2D
from matplotlib.text import Text as MplText

from .loader import load_images, validate_image_folder
from .annotations import Arrow, Rect, Oval, TextBox, LinkedGroup, render_annotations
from .saver import save_annotated_stack, collect_annotations


SETTINGS = None


def _load_settings():
    default = {
        'bg_color': '#2b2b2b',
        'slider_x': 0.94,
        'slider_w': 0.02,
        'slider_scale': 0.9,
        'save_format': 'jpeg',
        'save_quality': 100,
    }
    path = os.path.join(os.path.dirname(__file__), '..', 'settings.json')
    path = os.path.abspath(path)
    if os.path.exists(path):
        with open(path) as f:
            return {**default, **json.load(f)}
    return default


SETTINGS = _load_settings()


class ImageStackViewer:

    def __init__(self, data_path=None):
        self.data_path = data_path
        self._loaded = False

        self._slices = []
        self.num_slices = 0
        self._slice_idx = 0
        self._vmin_max = []

        self._annotations = {}
        self._patches = []
        self._handle_patches = []
        self._active_tool = None
        self._drawing = False
        self._draw_start = None
        self._draw_preview = None
        self._im = None
        self._selected_anno = None
        self._dragging = False
        self._drag_mode = None
        self._drag_start = None
        self._hovered_btn = None

        self._stamp_mode = False
        self._stamp_eligible = False
        self._ghost_patch = None
        self._linked_groups = []

        self._palette_axes = []
        self._palette_visible = False
        self._current_color = self.PALETTE_COLORS_RGB[0]
        self._selected_palette_idx = 0

        self.fig = plt.figure(figsize=(10, 10))
        self.fig.set_facecolor(SETTINGS['bg_color'])
        self.fig.canvas.manager.set_window_title('RadStack Annotator')

        margin = 0.02
        button_h = 0.04
        btn_gap = 0.02
        bar_w = 0.90

        tool_labels = ['\u2192  Arrow', '\u25ad  Rectangle', '\u25ef  Oval', '[T]  Text']
        action_labels = ['Open Folder', 'Save Images', 'Save Video', '\u21ba  Reset', '\u21c4  Invert']

        self._tool_btns = {}

        btn_w1 = (bar_w - (len(tool_labels) - 1) * btn_gap) / len(tool_labels)
        for i, label in enumerate(tool_labels):
            x = margin + i * (btn_w1 + btn_gap)
            ax = self.fig.add_axes([x, margin + button_h + btn_gap, btn_w1, button_h])
            ax.set_facecolor('#4a4a4a')
            ax.text(0.5, 0.5, label, ha='center', va='center',
                    color='white', fontsize=11, fontweight='bold',
                    transform=ax.transAxes, zorder=10)
            ax.set_xticks([])
            ax.set_yticks([])
            self._tool_btns[label] = ax

        btn_w2 = (bar_w - (len(action_labels) - 1) * btn_gap) / len(action_labels)
        for i, label in enumerate(action_labels):
            x = margin + i * (btn_w2 + btn_gap)
            ax = self.fig.add_axes([x, margin, btn_w2, button_h])
            ax.set_facecolor('#4a4a4a')
            ax.text(0.5, 0.5, label, ha='center', va='center',
                    color='white', fontsize=11, fontweight='bold',
                    transform=ax.transAxes, zorder=10)
            ax.set_xticks([])
            ax.set_yticks([])
            self._tool_btns[label] = ax

        img_y = margin + 2 * (button_h + btn_gap)
        img_h = 1.0 - img_y - margin
        self.ax = self.fig.add_axes([margin, img_y, 0.90, img_h])
        self.ax.set_facecolor(SETTINGS['bg_color'])
        self._show_placeholder()

        self.fig.canvas.draw()
        self.fig.canvas.mpl_connect('resize_event', self._on_resize)
        self.fig.canvas.mpl_connect('scroll_event', self._on_scroll)
        self.fig.canvas.mpl_connect('button_press_event', self._on_press)
        self.fig.canvas.mpl_connect('button_release_event', self._on_release)
        self.fig.canvas.mpl_connect('motion_notify_event', self._on_motion)
        self.fig.canvas.mpl_connect('key_press_event', self._on_key_press)

        if data_path is not None:
            self._load_folder(data_path)

        self.fig.canvas.manager.show()
        plt.show()

    # ------------------------------------------------------------------
    # Folder loading
    # ------------------------------------------------------------------

    def _open_folder_dialog(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_dir = os.path.join(base, 'images')
        folder = filedialog.askdirectory(
            title='Select folder with images',
            initialdir=default_dir if os.path.isdir(default_dir) else base,
        )
        if folder:
            self._load_folder(folder)

    def _reset_data_state(self):
        self._slices = []
        self.num_slices = 0
        self._slice_idx = 0
        self._vmin_max = []
        self._annotations = {}
        self._linked_groups = []
        self._selected_anno = None
        self._active_tool = None
        self._stamp_mode = False
        self._stamp_eligible = False
        self._drawing = False
        self._draw_start = None
        self._draw_preview = None
        self._loaded = False
        self._im = None
        self._current_color = self.PALETTE_COLORS_RGB[0]
        self._selected_palette_idx = 0
        self._hide_palette()
        self._clear_patches()
        if hasattr(self, '_slider'):
            try:
                self._slider.ax.remove()
            except Exception:
                pass
            del self._slider

    def _load_folder(self, data_path):
        valid, msg = validate_image_folder(data_path)
        if not valid:
            messagebox.showerror('Invalid Folder', msg)
            return

        self._reset_data_state()
        self.data_path = data_path
        self._slices = load_images(data_path)
        self.num_slices = len(self._slices)
        self._slice_idx = 0
        self._precompute_windowing()
        self._loaded = True

        self._show_slice()
        self._create_slider()
        self._set_button_colors()
        self.fig.canvas.draw_idle()

    def _show_placeholder(self):
        self.ax.clear()
        self.ax.text(0.5, 0.5,
                     'Click "Open Folder"\nto load JPG or PNG images',
                     ha='center', va='center', color='white', fontsize=18,
                     transform=self.ax.transAxes, zorder=20)
        self.ax.axis('off')

    def _create_slider(self):
        ax_bbox = self.ax.get_position()
        ax_y = ax_bbox.y0
        ax_h = ax_bbox.height
        slider_w = SETTINGS['slider_w'] * SETTINGS['slider_scale']
        slider_x = SETTINGS['slider_x'] + (SETTINGS['slider_w'] - slider_w) / 2
        new_h = ax_h * SETTINGS['slider_scale']
        new_y = ax_y + ax_h * (1 - SETTINGS['slider_scale']) / 2

        slider_ax = self.fig.add_axes([slider_x, new_y, slider_w, new_h])
        slider_ax.set_facecolor('#3c3c3c')

        self._slider = Slider(
            ax=slider_ax, label='',
            valmin=0, valmax=self.num_slices - 1,
            valinit=self.num_slices - 1, valstep=1,
            orientation='vertical',
            track_color='#555555',
            handle_style={'facecolor': '#aaaaaa', 'size': 10},
        )
        self._slider.on_changed(self._on_slider)
        self._slider_active = False

    # ------------------------------------------------------------------
    # Tool activation
    # ------------------------------------------------------------------

    TOOL_BY_LABEL = {'\u2192  Arrow': 'arrow', '\u25ad  Rectangle': 'rect', '\u25ef  Oval': 'oval', '[T]  Text': 'text'}
    ACTIVE_COLOR = '#5bb8f7'

    PALETTE_COLORS = ['#00e5ff', '#ffee58', '#ff9100', '#ff4081', '#76ff03', '#e040fb', '#ffffff', '#ff1744']
    PALETTE_COLORS_RGB = [
        (0, 229, 255), (255, 238, 88), (255, 145, 0), (255, 64, 129),
        (118, 255, 3), (224, 64, 251), (255, 255, 255), (255, 23, 68),
    ]

    def _set_button_colors(self):
        for label, ax in self._tool_btns.items():
            tid = self.TOOL_BY_LABEL.get(label)
            active = (tid is not None and self._active_tool == tid)
            ax.set_facecolor(self.ACTIVE_COLOR if active else '#4a4a4a')

    def _show_palette(self):
        if self._palette_visible:
            self._hide_palette()
        n = len(self.PALETTE_COLORS)
        margin = 0.02
        button_h = 0.04
        btn_gap = 0.02
        img_y = margin + 2 * (button_h + btn_gap)
        img_h = 1.0 - img_y - margin
        gap = 0.004
        palette_x = 0.0
        palette_w = 0.028
        swatch_h = (img_h - (n - 1) * gap) / n
        for i in range(n):
            y = img_y + i * (swatch_h + gap)
            ax = self.fig.add_axes([palette_x, y, palette_w, swatch_h])
            ax.set_facecolor(self.PALETTE_COLORS[i])
            ax.set_xticks([])
            ax.set_yticks([])
            if i == self._selected_palette_idx:
                for sp in ax.spines.values():
                    sp.set_color('white')
                    sp.set_linewidth(2.5)
            else:
                for sp in ax.spines.values():
                    sp.set_color('#333333')
                    sp.set_linewidth(0.5)
            self._palette_axes.append(ax)
        self._palette_visible = True
        self.fig.canvas.draw_idle()

    def _hide_palette(self):
        for ax in self._palette_axes:
            try:
                ax.remove()
            except Exception:
                pass
        self._palette_axes = []
        self._palette_visible = False

    def _handle_tool_click(self, label):
        if label == 'Open Folder':
            self._open_folder_dialog()
            return
        if label == 'Save Images':
            if not self._loaded:
                messagebox.showwarning('No Data', 'No images loaded.')
                return
            self._active_tool = 'save_images'
            self._set_button_colors()
            self.fig.canvas.draw_idle()
            try:
                self.fig.canvas.manager.window.update()
            except Exception:
                pass
            self._save_stack()
            self._active_tool = None
            self._set_button_colors()
            self.fig.canvas.draw_idle()
            return
        if label == 'Save Video':
            if not self._loaded:
                messagebox.showwarning('No Data', 'No images loaded.')
                return
            self._active_tool = 'save_video'
            self._set_button_colors()
            self.fig.canvas.draw_idle()
            try:
                self.fig.canvas.manager.window.update()
            except Exception:
                pass
            self._save_video()
            self._active_tool = None
            self._set_button_colors()
            self.fig.canvas.draw_idle()
            return
        if label == '\u21ba  Reset':
            if not self._loaded:
                return
            self._active_tool = 'reset'
            self._set_button_colors()
            self.fig.canvas.draw_idle()
            try:
                self.fig.canvas.manager.window.update()
            except Exception:
                pass
            self._reset_all()
            self._active_tool = None
            self._set_button_colors()
            self.fig.canvas.draw_idle()
            return
        if label == '\u21c4  Invert':
            if not self._loaded:
                return
            self._active_tool = 'invert'
            self._set_button_colors()
            self.fig.canvas.draw_idle()
            try:
                self.fig.canvas.manager.window.update()
            except Exception:
                pass
            self._invert_order()
            self._active_tool = None
            self._set_button_colors()
            self.fig.canvas.draw_idle()
            return
        tid = self.TOOL_BY_LABEL.get(label)
        if tid is None:
            return
        if not self._loaded:
            messagebox.showwarning('No Data', 'Load a folder first.')
            return
        if self._active_tool == tid:
            self._active_tool = None
            self.fig.canvas.set_cursor(cursors.POINTER)
            self._hide_palette()
        else:
            self._active_tool = tid
            self.fig.canvas.set_cursor(cursors.HAND if tid == 'arrow' else cursors.POINTER)
            self._show_palette()
        self._set_button_colors()
        self._update_title()
        self.fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_stack(self, event=None):
        if not self._loaded:
            return
        save_annotated_stack(
            self._slices, self._annotations, self._linked_groups,
            self.data_path, SETTINGS,
        )
        out_dir = self.data_path.rstrip('/') + '_annotated'
        messagebox.showinfo('Save Complete', f'Annotated images saved to:\n{out_dir}')

    def _save_video(self):
        if not self._loaded:
            return
        quality = SETTINGS.get('save_quality', 100)
        tmp = tempfile.mkdtemp(prefix='radstack_video_')
        try:
            for idx, arr in enumerate(self._slices):
                annos = collect_annotations(self._annotations, self._linked_groups, idx)
                rendered = render_annotations(arr, annos) if annos else arr.copy()
                if rendered.dtype in (np.float32, np.float64):
                    rendered = (np.clip(rendered, 0, 1) * 255).astype(np.uint8)
                PILImage.fromarray(rendered).save(
                    os.path.join(tmp, f'frame_{idx:04d}.jpg'),
                    quality=quality, subsampling=0,
                )

            list_file = os.path.join(tmp, 'ffmpeg_list.txt')
            with open(list_file, 'w') as f:
                for idx in range(len(self._slices)):
                    f.write(f"file 'frame_{idx:04d}.jpg'\n")

            out_path = os.path.join(os.path.dirname(self.data_path.rstrip('/')), 'annotated-video.mp4')

            subprocess.run([
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0', '-i', list_file,
                '-r', '30',
                '-c:v', 'libx264',
                '-x264-params', 'keyint=1:min-keyint=1:no-scenecut=1',
                '-crf', '18',
                '-pix_fmt', 'yuv420p',
                out_path,
            ], check=True)

            messagebox.showinfo('Save Complete', f'Video saved to:\n{out_path}')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _reset_all(self):
        if self._drawing:
            self._cancel_drawing()
        self._stamp_mode = False
        self._stamp_eligible = False
        self._annotations = {}
        self._linked_groups = []
        self._selected_anno = None
        self._active_tool = None
        self._current_color = self.PALETTE_COLORS_RGB[0]
        self._selected_palette_idx = 0
        self._hide_palette()
        self._clear_patches()
        self._redraw_annotations()
        self._set_button_colors()
        self._update_title()
        self.fig.canvas.draw_idle()
        print('Reset — all annotations cleared')

    def _invert_order(self):
        if not self._loaded:
            return
        n = self.num_slices
        if n == 0:
            return
        self._slices = list(reversed(self._slices))
        self._vmin_max = list(reversed(self._vmin_max))

        new_annotations = {}
        for idx, annos in self._annotations.items():
            new_idx = n - 1 - idx
            for a in annos:
                a.slice_idx = new_idx
            new_annotations[new_idx] = annos
        self._annotations = new_annotations

        for group in self._linked_groups:
            group.start_slice = n - 1 - group.start_slice
            group.end_slice = n - 1 - group.end_slice

        self._slice_idx = 0
        self._selected_anno = None
        self._stamp_mode = False

        if hasattr(self, '_slider'):
            self._slider.valmax = n - 1
            self._slider.ax.set_ylim(0, n - 1)
            self._slider_active = True
            self._slider.set_val(n - 1)
            self._slider_active = False

        self._show_slice()
        self.fig.canvas.draw_idle()
        print(f'Image order inverted — now showing slice 1/{n}')

    # ------------------------------------------------------------------
    # Windowing
    # ------------------------------------------------------------------

    def _precompute_windowing(self):
        self._vmin_max = []
        for arr in self._slices:
            self._vmin_max.append((arr.min(), arr.max()))

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _update_title(self):
        if not self._loaded:
            self.ax.set_title('', fontsize=12, color='white')
            return
        info = f'Image {self._slice_idx + 1}/{self.num_slices}'
        if self._active_tool:
            info += f'  [{self._active_tool}]'
        if self._stamp_mode:
            info += '  [stamp]'
        self.ax.set_title(info, fontsize=12, color='white')

    def _show_slice(self):
        if not self._loaded:
            return
        arr = self._slices[self._slice_idx]
        vmin, vmax = self._vmin_max[self._slice_idx]

        if self._im is None:
            self.ax.clear()
            self._im = self.ax.imshow(arr, cmap='gray', vmin=vmin, vmax=vmax)
            self.ax.axis('off')
        else:
            self._im.set_data(arr)
            self._im.set_clim(vmin, vmax)

        self._update_title()

        if hasattr(self, '_slider') and not self._slider_active:
            self._slider_active = True
            self._slider.set_val((self.num_slices - 1) - self._slice_idx)
            self._slider_active = False

        self._redraw_annotations()
        self.fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Annotation management
    # ------------------------------------------------------------------

    def _get_annotations(self, idx=None):
        if idx is None:
            idx = self._slice_idx
        return self._annotations.get(idx, [])

    def _add_annotation(self, anno):
        idx = anno.slice_idx
        if idx not in self._annotations:
            self._annotations[idx] = []
        self._annotations[idx].append(anno)

    def _remove_annotation(self, anno):
        idx = anno.slice_idx
        if idx in self._annotations and anno in self._annotations[idx]:
            self._annotations[idx].remove(anno)
        for g in self._linked_groups[:]:
            if anno is g.start_anno:
                if g.end_anno in self._annotations.get(g.end_slice, []):
                    self._annotations[g.end_slice].remove(g.end_anno)
                self._linked_groups.remove(g)
            elif anno is g.end_anno:
                if g.start_anno in self._annotations.get(g.start_slice, []):
                    self._annotations[g.start_slice].remove(g.start_anno)
                self._linked_groups.remove(g)

    def _clear_patches(self):
        for p in self._patches:
            p.remove()
        self._patches = []
        for p in self._handle_patches:
            p.remove()
        self._handle_patches = []
        if self._ghost_patch is not None:
            self._ghost_patch.remove()
            self._ghost_patch = None

    def _redraw_annotations(self):
        self._clear_patches()

        for anno in self._get_annotations():
            self._draw_annotation_patch(anno)

        for group in self._linked_groups:
            if group.contains_slice(self._slice_idx):
                interp = group.get_interpolated(self._slice_idx)
                self._draw_annotation_patch(interp, lw=2)

    def _draw_annotation_patch(self, anno, color=None, lw=None):
        is_selected = (anno is self._selected_anno
                       and anno.slice_idx == self._slice_idx)
        c = color or ('cyan' if is_selected else self._anno_color(anno))
        w = lw or (3 if is_selected else 2)
        x1, y1, x2, y2 = anno.x1, anno.y1, anno.x2, anno.y2

        if isinstance(anno, TextBox):
            bx, by = min(x1, x2), min(y1, y2)
            rw, rh = abs(x2 - x1), abs(y2 - y1)
            bg = MplRect((bx, by), rw, rh,
                         linewidth=w, edgecolor=c, facecolor='black',
                         alpha=0.5, zorder=5)
            self.ax.add_patch(bg)
            self._patches.append(bg)
            txt = MplText((x1 + x2) / 2, (y1 + y2) / 2, anno.text,
                          color=c, fontsize=10, fontweight='bold',
                          ha='center', va='center', zorder=6)
            self.ax.add_artist(txt)
            self._patches.append(txt)
        elif isinstance(anno, Rect):
            bx, by = min(x1, x2), min(y1, y2)
            rw, rh = abs(x2 - x1), abs(y2 - y1)
            patch = MplRect((bx, by), rw, rh,
                            linewidth=w, edgecolor=c, facecolor='none', zorder=5)
            self.ax.add_patch(patch)
            self._patches.append(patch)
        elif isinstance(anno, Oval):
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            ew, eh = abs(x2 - x1), abs(y2 - y1)
            patch = Ellipse((cx, cy), ew, eh,
                            linewidth=w, edgecolor=c, facecolor='none', zorder=5)
            self.ax.add_patch(patch)
            self._patches.append(patch)
        else:
            patch = FancyArrowPatch(
                (x1, y1), (x2, y2),
                arrowstyle='-|>', mutation_scale=20,
                color=c, linewidth=w, zorder=5,
            )
            self.ax.add_patch(patch)
            self._patches.append(patch)
        if is_selected:
            pts = [(x1, y1), (x2, y2)]
            if not isinstance(anno, Arrow):
                pts = [(x1, y1), (x1, y2), (x2, y1), (x2, y2)]
            for px, py in pts:
                h = Circle((px, py), radius=5, facecolor='cyan',
                           edgecolor='white', linewidth=1.5, zorder=10)
                self.ax.add_patch(h)
                self._handle_patches.append(h)

    def _anno_color(self, anno):
        return tuple(c / 255 for c in anno.color)

    # ------------------------------------------------------------------
    # Stamp mode
    # ------------------------------------------------------------------

    def _enter_stamp_mode(self):
        if (self._selected_anno is not None
                and self._selected_anno.slice_idx != self._slice_idx):
            self._stamp_mode = True
            self.fig.canvas.set_cursor(cursors.HAND)
            self._update_title()
            self._redraw_annotations()
            self.fig.canvas.draw_idle()

    def _exit_stamp_mode(self):
        if self._stamp_mode:
            self._stamp_mode = False
            self._clear_patches()
            self._redraw_annotations()
            self._update_title()
            self.fig.canvas.draw_idle()

    def _is_linked_anchor(self, anno):
        for g in self._linked_groups:
            if anno is g.start_anno or anno is g.end_anno:
                return g
        return None

    def _update_ghost(self, x, y):
        src = self._selected_anno
        if src is None:
            return
        dx = src.x2 - src.x1
        dy = src.y2 - src.y1
        x1 = x - dx / 2
        y1 = y - dy / 2
        x2 = x + dx / 2
        y2 = y + dy / 2
        if self._ghost_patch is None:
            if isinstance(src, (Rect, TextBox)):
                bx, by = min(x1, x2), min(y1, y2)
                rw, rh = abs(x2 - x1), abs(y2 - y1)
                self._ghost_patch = MplRect(
                    (bx, by), rw, rh,
                    linewidth=2, edgecolor='cyan', facecolor='none',
                    linestyle='--', zorder=7,
                )
            elif isinstance(src, Oval):
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                ew, eh = abs(x2 - x1), abs(y2 - y1)
                self._ghost_patch = Ellipse(
                    (cx, cy), ew, eh,
                    linewidth=2, edgecolor='cyan', facecolor='none',
                    linestyle='--', zorder=7,
                )
            else:
                self._ghost_patch = FancyArrowPatch(
                    (x1, y1), (x2, y2),
                    arrowstyle='-|>', mutation_scale=20,
                    color='cyan', linewidth=3, zorder=7,
                )
            self.ax.add_patch(self._ghost_patch)
        else:
            if isinstance(self._ghost_patch, MplRect):
                bx, by = min(x1, x2), min(y1, y2)
                self._ghost_patch.set_xy((bx, by))
                self._ghost_patch.set_width(abs(x2 - x1))
                self._ghost_patch.set_height(abs(y2 - y1))
            elif isinstance(self._ghost_patch, Ellipse):
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                self._ghost_patch.center = (cx, cy)
                self._ghost_patch.width = abs(x2 - x1)
                self._ghost_patch.height = abs(y2 - y1)
            else:
                self._ghost_patch.set_positions((x1, y1), (x2, y2))
        self.fig.canvas.draw_idle()

    def _do_stamp(self, x, y):
        src = self._selected_anno
        if src is None or src.slice_idx == self._slice_idx:
            return

        dx = src.x2 - src.x1
        dy = src.y2 - src.y1
        dst = src.copy_transformed(x - dx / 2, y - dy / 2,
                                   x + dx / 2, y + dy / 2,
                                   self._slice_idx)
        self._add_annotation(dst)
        group = LinkedGroup(src.slice_idx, self._slice_idx, src, dst)
        self._linked_groups.append(group)
        kind = type(src).__name__
        print(f'Stamped {kind} from slice {src.slice_idx} → {self._slice_idx}'
              f' (interpolating {group.start_slice}–{group.end_slice})')
        self._selected_anno = None
        self._exit_stamp_mode()
        self._active_tool = None
        self._hide_palette()
        self._set_button_colors()
        self._update_title()
        self.fig.canvas.draw_idle()

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def _cancel_drawing(self):
        if self._draw_preview is not None:
            self._draw_preview.remove()
            self._draw_preview = None
        self._drawing = False
        self._draw_start = None
        self._update_title()
        self.fig.canvas.draw_idle()

    def _on_press(self, event):
        if event.inaxes is None:
            return

        for label, ax in self._tool_btns.items():
            if event.inaxes == ax:
                if self._drawing:
                    self._cancel_drawing()
                self._handle_tool_click(label)
                return

        for i, ax in enumerate(self._palette_axes):
            if event.inaxes == ax:
                self._current_color = self.PALETTE_COLORS_RGB[i]
                self._selected_palette_idx = i
                self._show_palette()
                return

        if event.inaxes != self.ax:
            return

        if not self._loaded:
            return

        x, y = event.xdata, event.ydata

        if self._stamp_mode:
            self._do_stamp(x, y)
            return

        if self._active_tool in ('arrow', 'rect', 'oval', 'text') and not self._drawing:
            self._drawing = True
            self._draw_start = (x, y)
            if self._active_tool == 'arrow':
                self._draw_preview = Line2D(
                    [x, x], [y, y],
                    color='red', linewidth=2, linestyle='--', zorder=6,
                )
                self.ax.add_line(self._draw_preview)
                self.fig.canvas.draw()
            elif self._active_tool == 'oval':
                self._draw_preview = Ellipse(
                    (x, y), 1, 1,
                    linewidth=2, edgecolor='red', facecolor='none',
                    linestyle='--', zorder=6,
                )
                self.ax.add_patch(self._draw_preview)
                self.fig.canvas.draw()
            else:
                self._draw_preview = MplRect(
                    (x, y), 1, 1,
                    linewidth=2, edgecolor='red', facecolor='none',
                    linestyle='--', zorder=6,
                )
                self.ax.add_patch(self._draw_preview)
                self.fig.canvas.draw()
            return

        if self._selected_anno is not None and self._selected_anno.slice_idx == self._slice_idx:
            mode = self._hit_test(x, y, self._selected_anno)
            if mode:
                return

        anno, mode = self._find_nearest(x, y)
        if anno is not None:
            self._selected_anno = anno
            self._stamp_eligible = False
            self._redraw_annotations()
            self.fig.canvas.draw_idle()
            return

        if self._selected_anno is not None:
            self._selected_anno = None
            self._stamp_eligible = False
            self._exit_stamp_mode()
            self._redraw_annotations()
            self.fig.canvas.draw_idle()

    def _on_release(self, event):
        if self._drawing and self._draw_start is not None:
            if event.inaxes != self.ax:
                self._cancel_drawing()
                return
            x1, y1 = self._draw_start
            x2, y2 = event.xdata, event.ydata
            if self._draw_preview is not None:
                self._draw_preview.remove()
                self._draw_preview = None
            if x2 is not None and y2 is not None and (abs(x2 - x1) > 5 or abs(y2 - y1) > 5):
                tool = self._active_tool
                cls = {'arrow': Arrow, 'rect': Rect, 'oval': Oval, 'text': TextBox}.get(tool, Arrow)
                kwargs = {}
                if self._current_color is not None:
                    kwargs['color'] = self._current_color
                anno = cls(x1, y1, x2, y2, self._slice_idx, **kwargs)
                if isinstance(anno, TextBox):
                    try:
                        root = self.fig.canvas.manager.window
                        txt = simpledialog.askstring('Text', 'Enter label:', parent=root)
                        anno.text = txt or ''
                    except Exception:
                        anno.text = ''
                self._add_annotation(anno)
                self._selected_anno = anno
                self._stamp_eligible = True
                self._redraw_annotations()
            self._drawing = False
            self._draw_start = None
            self._update_title()
            self.fig.canvas.draw_idle()
            return

        if self._dragging and self._selected_anno is not None:
            group = self._is_linked_anchor(self._selected_anno)
            if group and self._selected_anno.slice_idx in (group.start_slice, group.end_slice):
                pass

        self._dragging = False
        self._drag_mode = None
        self._drag_start = None

    def _on_key_press(self, event):
        if event.key in ('delete', 'backspace') and self._selected_anno is not None:
            anno = self._selected_anno
            self._selected_anno = None
            self._stamp_eligible = False
            self._exit_stamp_mode()
            self._remove_annotation(anno)
            self._redraw_annotations()
            self.fig.canvas.draw_idle()

    def _on_motion(self, event):
        held_label = None
        for label, ax in self._tool_btns.items():
            if event.inaxes == ax:
                held_label = label
                break

        if held_label != self._hovered_btn:
            self._hovered_btn = held_label
            self._set_button_colors()
            if self._hovered_btn is not None:
                ax = self._tool_btns[self._hovered_btn]
                tid = self.TOOL_BY_LABEL.get(self._hovered_btn)
                is_active = (tid is not None and self._active_tool == tid)
                ax.set_facecolor('#7cc9f9' if is_active else '#5c5c5c')
            self.fig.canvas.draw_idle()
            return

        if held_label is not None:
            return

        if event.inaxes != self.ax:
            return

        if not self._loaded:
            return

        x, y = event.xdata, event.ydata

        if self._stamp_mode and self._selected_anno is not None:
            self._update_ghost(x, y)
            return

        if self._drawing and self._draw_preview is not None:
            x1, y1 = self._draw_start
            if isinstance(self._draw_preview, Line2D):
                self._draw_preview.set_data([x1, x], [y1, y])
            elif isinstance(self._draw_preview, Ellipse):
                cx, cy = (x1 + x) / 2, (y1 + y) / 2
                self._draw_preview.center = (cx, cy)
                self._draw_preview.width = abs(x - x1)
                self._draw_preview.height = abs(y - y1)
            else:
                bx, by = min(x1, x), min(y1, y)
                rw, rh = abs(x - x1), abs(y - y1)
                self._draw_preview.set_xy((bx, by))
                self._draw_preview.set_width(rw)
                self._draw_preview.set_height(rh)
            self.fig.canvas.draw()
            return

        if not self._dragging or self._selected_anno is None:
            return

        if getattr(self._selected_anno, 'locked', False):
            self._dragging = False
            self._drag_mode = None
            self._drag_start = None
            return

        if self._drag_mode == 'body' and self._drag_start is not None:
            new_mx = x - self._drag_start[0]
            new_my = y - self._drag_start[1]
            old_mx, old_my = self._selected_anno.midpoint()
            self._selected_anno.translate(new_mx - old_mx, new_my - old_my)
        elif self._drag_mode == 'head':
            self._selected_anno.x2 = x
            self._selected_anno.y2 = y
        elif self._drag_mode == 'tail':
            self._selected_anno.x1 = x
            self._selected_anno.y1 = y

        self._redraw_annotations()
        self.fig.canvas.draw_idle()

    def _hit_test(self, x, y, anno, tol=12):
        if isinstance(anno, Arrow):
            if anno.end_dist(x, y) < tol:
                return 'head'
            if anno.start_dist(x, y) < tol:
                return 'tail'
            if anno.line_dist(x, y) < tol:
                return 'body'
            return None
        x1, y1, x2, y2 = anno.x1, anno.y1, anno.x2, anno.y2
        for (cx, cy) in [(x1, y1), (x1, y2), (x2, y1), (x2, y2)]:
            if math.hypot(x - cx, y - cy) < tol:
                return 'head' if (cx, cy) == (x2, y2) else 'tail'
        if isinstance(anno, Oval):
            rx, ry = abs(x2 - x1) / 2, abs(y2 - y1) / 2
            if rx < 1 or ry < 1:
                return None
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                return 'body'
        else:
            if min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
                return 'body'
        return None

    def _find_nearest(self, x, y, tol=15):
        for anno in self._get_annotations():
            mode = self._hit_test(x, y, anno, tol)
            if mode:
                return anno, mode
        return None, None

    # ------------------------------------------------------------------
    # Slider / Scroll
    # ------------------------------------------------------------------

    def _on_slider(self, val):
        if not self._loaded:
            return
        old_idx = self._slice_idx
        self._slice_idx = (self.num_slices - 1) - int(val)
        if self._selected_anno is not None:
            if self._selected_anno.slice_idx != self._slice_idx:
                if self._stamp_eligible and not self._stamp_mode:
                    self._enter_stamp_mode()
            else:
                if self._stamp_mode:
                    self._exit_stamp_mode()
        self._show_slice()

    def _reposition_slider_to_image(self):
        ax_bbox = self.ax.get_position()
        ax_y = ax_bbox.y0
        ax_h = ax_bbox.height
        slider_w = SETTINGS['slider_w'] * SETTINGS['slider_scale']
        slider_x = SETTINGS['slider_x'] + (SETTINGS['slider_w'] - slider_w) / 2
        new_h = ax_h * SETTINGS['slider_scale']
        new_y = ax_y + ax_h * (1 - SETTINGS['slider_scale']) / 2
        self._slider.ax.set_position([slider_x, new_y, slider_w, new_h])

    def _on_resize(self, event):
        if hasattr(self, '_slider'):
            self._reposition_slider_to_image()
        if self._palette_visible:
            self._show_palette()

    def _on_scroll(self, event):
        if not self._loaded:
            return
        old_idx = self._slice_idx
        if event.button == 'up':
            self._slice_idx = max(0, self._slice_idx - 1)
        elif event.button == 'down':
            self._slice_idx = min(self.num_slices - 1, self._slice_idx + 1)
        if self._slice_idx != old_idx:
            if (self._selected_anno is not None
                    and self._selected_anno.slice_idx != self._slice_idx):
                if self._stamp_eligible and not self._stamp_mode:
                    self._enter_stamp_mode()
            elif self._stamp_mode and self._selected_anno is not None:
                if self._selected_anno.slice_idx == self._slice_idx:
                    self._exit_stamp_mode()
        self._show_slice()
