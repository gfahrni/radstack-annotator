import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont


_FONT_CACHE = {}


def _get_font(size):
    if size not in _FONT_CACHE:
        try:
            _FONT_CACHE[size] = ImageFont.truetype("Arial.ttf", size)
        except (OSError, IOError):
            try:
                _FONT_CACHE[size] = ImageFont.truetype("DejaVuSans.ttf", size)
            except (OSError, IOError):
                _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


class Arrow:

    def __init__(self, x1, y1, x2, y2, slice_idx, color=(255, 50, 50), width=3):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.slice_idx = slice_idx
        self.color = color
        self.width = width
        self.locked = False

    def midpoint(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def translate(self, dx, dy):
        self.x1 += dx
        self.y1 += dy
        self.x2 += dx
        self.y2 += dy

    def start_dist(self, px, py):
        return math.hypot(self.x1 - px, self.y1 - py)

    def end_dist(self, px, py):
        return math.hypot(self.x2 - px, self.y2 - py)

    def line_dist(self, px, py):
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        if dx == 0 and dy == 0:
            return self.start_dist(px, py)
        t = max(0, min(1, ((px - self.x1) * dx + (py - self.y1) * dy) / (dx*dx + dy*dy)))
        proj_x = self.x1 + t * dx
        proj_y = self.y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def copy_transformed(self, x1, y1, x2, y2, slice_idx):
        return Arrow(x1, y1, x2, y2, slice_idx, self.color, self.width)

    def copy(self, slice_idx):
        return Arrow(self.x1, self.y1, self.x2, self.y2, slice_idx, self.color, self.width)


class Rect:

    def __init__(self, x1, y1, x2, y2, slice_idx, color=(50, 180, 255), width=3):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.slice_idx = slice_idx
        self.color = color
        self.width = width
        self.locked = False

    def midpoint(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def translate(self, dx, dy):
        self.x1 += dx
        self.y1 += dy
        self.x2 += dx
        self.y2 += dy

    def copy_transformed(self, x1, y1, x2, y2, slice_idx):
        return Rect(x1, y1, x2, y2, slice_idx, self.color, self.width)

    def copy(self, slice_idx):
        return Rect(self.x1, self.y1, self.x2, self.y2, slice_idx, self.color, self.width)


class Oval:

    def __init__(self, x1, y1, x2, y2, slice_idx, color=(50, 255, 150), width=3):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.slice_idx = slice_idx
        self.color = color
        self.width = width
        self.locked = False

    def midpoint(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def translate(self, dx, dy):
        self.x1 += dx
        self.y1 += dy
        self.x2 += dx
        self.y2 += dy

    def copy_transformed(self, x1, y1, x2, y2, slice_idx):
        return Oval(x1, y1, x2, y2, slice_idx, self.color, self.width)

    def copy(self, slice_idx):
        return Oval(self.x1, self.y1, self.x2, self.y2, slice_idx, self.color, self.width)


class TextBox:

    def __init__(self, x1, y1, x2, y2, slice_idx, text='',
                 color=(255, 255, 255), width=3, font_size=10, show_background=True):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.slice_idx = slice_idx
        self.text = text
        self.color = color
        self.width = width
        self.font_size = font_size
        self.show_background = show_background
        self.locked = False

    def midpoint(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    def translate(self, dx, dy):
        self.x1 += dx
        self.y1 += dy
        self.x2 += dx
        self.y2 += dy

    def copy_transformed(self, x1, y1, x2, y2, slice_idx):
        return TextBox(x1, y1, x2, y2, slice_idx, self.text, self.color, self.width, self.font_size, self.show_background)

    def copy(self, slice_idx):
        return TextBox(self.x1, self.y1, self.x2, self.y2, slice_idx, self.text, self.color, self.width, self.font_size, self.show_background)


class LinkedGroup:

    def __init__(self, start_slice, end_slice, start_anno, end_anno):
        if start_slice <= end_slice:
            self.start_slice = start_slice
            self.end_slice = end_slice
            self.start_anno = start_anno
            self.end_anno = end_anno
        else:
            self.start_slice = end_slice
            self.end_slice = start_slice
            self.start_anno = end_anno
            self.end_anno = start_anno

    def contains_slice(self, idx):
        return self.start_slice < idx < self.end_slice

    def get_interpolated(self, idx):
        if idx <= self.start_slice:
            return self.start_anno
        if idx >= self.end_slice:
            return self.end_anno
        t = (idx - self.start_slice) / (self.end_slice - self.start_slice)
        # Interpolate position only; size is fixed from start_anno
        w = abs(self.start_anno.x2 - self.start_anno.x1)
        h = abs(self.start_anno.y2 - self.start_anno.y1)
        sx = 1 if self.start_anno.x2 >= self.start_anno.x1 else -1
        sy = 1 if self.start_anno.y2 >= self.start_anno.y1 else -1
        x1 = self.start_anno.x1 + t * (self.end_anno.x1 - self.start_anno.x1)
        y1 = self.start_anno.y1 + t * (self.end_anno.y1 - self.start_anno.y1)
        x2 = x1 + sx * w
        y2 = y1 + sy * h
        return self.start_anno.copy_transformed(x1, y1, x2, y2, idx)


def _draw_arrowhead(draw, x, y, dx, dy, color, size=12):
    angle = math.atan2(dy, dx)
    spread = math.pi / 6
    tip1 = (x - size * math.cos(angle - spread),
            y - size * math.sin(angle - spread))
    tip2 = (x - size * math.cos(angle + spread),
            y - size * math.sin(angle + spread))
    draw.polygon([(x, y), tip1, tip2], fill=color)


_RENDER_SCALE = 2


def render_annotations(image_array, annotations):
    if image_array.dtype in (np.float32, np.float64):
        img = Image.fromarray((np.clip(image_array, 0, 1) * 255).astype(np.uint8))
    elif image_array.dtype == np.uint8:
        img = Image.fromarray(image_array)
    else:
        img = Image.fromarray(image_array.astype(np.uint8))

    if img.mode != 'RGB':
        img = img.convert('RGB')

    if not annotations:
        result = np.array(img)
        if image_array.dtype in (np.float32, np.float64):
            result = result.astype(np.float32) / 255.0
        return result

    s = _RENDER_SCALE
    orig_size = img.size
    img = img.resize((orig_size[0] * s, orig_size[1] * s), Image.NEAREST)

    text_boxes = [a for a in annotations if isinstance(a, TextBox)]
    others = [a for a in annotations if not isinstance(a, TextBox)]

    draw = ImageDraw.Draw(img)
    for ann in others:
        x1, y1, x2, y2 = ann.x1 * s, ann.y1 * s, ann.x2 * s, ann.y2 * s
        w = ann.width * s
        if isinstance(ann, Rect):
            draw.rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                           outline=ann.color, width=w)
        elif isinstance(ann, Oval):
            draw.ellipse([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                         outline=ann.color, width=w)
        else:
            dx = x2 - x1
            dy = y2 - y1
            draw.line([(x1, y1), (x2, y2)], fill=ann.color, width=w)
            _draw_arrowhead(draw, x2, y2, dx, dy, ann.color, size=12 * s)

    if text_boxes:
        img = img.convert('RGBA')
        for ann in text_boxes:
            font = _get_font(max(1, int(ann.font_size * s)))
            x1, y1, x2, y2 = ann.x1 * s, ann.y1 * s, ann.x2 * s, ann.y2 * s
            if ann.show_background:
                overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
                od = ImageDraw.Draw(overlay)
                od.rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                             fill=(0, 0, 0, 128), outline=ann.color, width=ann.width * s)
                img = Image.alpha_composite(img, overlay)
        img = img.convert('RGB')
        draw = ImageDraw.Draw(img)
        for ann in text_boxes:
            font = _get_font(max(1, int(ann.font_size * s)))
            bbox = draw.textbbox((0, 0), ann.text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (ann.x1 + ann.x2) * s / 2 - tw / 2
            ty = (ann.y1 + ann.y2) * s / 2 - th / 2
            draw.text((tx, ty), ann.text, fill=ann.color, font=font)

    img = img.resize(orig_size, Image.BOX)

    result = np.array(img)
    if image_array.dtype in (np.float32, np.float64):
        result = result.astype(np.float32) / 255.0

    return result
