"""
Export logic for RadStack Annotator.

Handles collecting annotations (including interpolated ones from linked groups)
and rendering the annotated image stack to disk.
"""

import os
import numpy as np
from PIL import Image as PILImage
from .annotations import render_annotations


def collect_annotations(annotations, linked_groups, idx):
    """Collect all annotations for slice *idx*, including interpolated ones."""
    result = list(annotations.get(idx, []))
    for group in linked_groups:
        if group.contains_slice(idx):
            result.append(group.get_interpolated(idx))
    return result


def save_annotated_stack(slices, annotations, linked_groups, data_path, settings):
    """Render annotations onto every slice and save the result to disk."""
    out_dir = data_path.rstrip('/') + '_annotated'
    os.makedirs(out_dir, exist_ok=True)

    fmt = settings.get('save_format', 'jpeg')
    quality = settings.get('save_quality', 100)

    for idx, arr in enumerate(slices):
        annos = collect_annotations(annotations, linked_groups, idx)
        if annos:
            rendered = render_annotations(arr, annos)
        else:
            rendered = arr.copy()

        if rendered.dtype in (np.float32, np.float64):
            rendered = (np.clip(rendered, 0, 1) * 255).astype(np.uint8)

        path = os.path.join(out_dir, f'slice_{idx:04d}.{fmt}')
        if fmt == 'jpeg':
            PILImage.fromarray(rendered).save(path, quality=quality, subsampling=0)
        else:
            PILImage.fromarray(rendered).save(path)

    print(f'Saved annotated stack to {out_dir} ({len(slices)} images)')
