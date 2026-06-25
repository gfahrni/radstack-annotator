"""
Data-loading utilities for RadStack Annotator.

Responsibilities:
    - Scan a directory for .jpg/.jpeg/.png files.
    - Validate that a folder contains only image files.
    - Read the images and return them as a list of numpy arrays.
"""

import os
import glob
import numpy as np
from PIL import Image as PILImage


VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png'}


def validate_image_folder(data_path):
    """
    Check that *data_path* is a directory containing only JPG/PNG files.

    Returns:
        (True, list_of_image_paths) on success, or
        (False, error_message) on failure.
    """
    if not os.path.isdir(data_path):
        return False, f"'{data_path}' is not a valid directory."

    files = sorted(
        glob.glob(os.path.join(data_path, '*.jp*g')) +
        glob.glob(os.path.join(data_path, '*.JPG')) +
        glob.glob(os.path.join(data_path, '*.png')) +
        glob.glob(os.path.join(data_path, '*.PNG'))
    )
    if not files:
        return False, "No JPG or PNG images found in the folder."

    invalid = []
    for f in os.listdir(data_path):
        if f.startswith('.'):
            continue
        full = os.path.join(data_path, f)
        if os.path.isdir(full):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext not in VALID_EXTENSIONS:
            invalid.append(f)

    if invalid:
        plural = 's' if len(invalid) > 1 else ''
        return (
            False,
            f"Folder contains non-image file{plural}: "
            f"{', '.join(invalid[:5])}"
        )

    return True, files


def load_images(data_path):
    """
    Find all JPG/PNG files in *data_path* sorted by name and load them.

    Args:
        data_path: Path to a directory containing image files.

    Returns:
        A list of numpy arrays (the loaded images). Empty if none found.
    """
    if not os.path.isdir(data_path):
        return []

    files = sorted(
        glob.glob(os.path.join(data_path, '*.jp*g')) +
        glob.glob(os.path.join(data_path, '*.JPG')) +
        glob.glob(os.path.join(data_path, '*.png')) +
        glob.glob(os.path.join(data_path, '*.PNG'))
    )
    if not files:
        return []

    print(f'Found {len(files)} images in {os.path.basename(data_path)}')

    images = []
    for f in files:
        arr = np.array(PILImage.open(f))
        images.append(arr)

    return images
