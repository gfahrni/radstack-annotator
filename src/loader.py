"""
Data-loading utilities for RadStack Annotator.

Responsibilities:
    - Scan a directory for .jpg/.jpeg files.
    - Read the images and return them as a list of numpy arrays.
"""

import os
import sys
import glob
import numpy as np
import matplotlib.image as mpimg


def load_images(data_path):
    """
    Find all JPG files in *data_path* sorted by name and load them.

    Args:
        data_path: Path to a directory containing .jpg/.jpeg files.

    Returns:
        A list of numpy arrays (the loaded images).
        Exits with an error if no images are found.
    """
    files = sorted(glob.glob(os.path.join(data_path, '*.jp*g')))
    if not files:
        print(f'No JPG files found in {data_path}.')
        sys.exit(1)

    print(f'Found {len(files)} images in {os.path.basename(data_path)}')

    images = []
    for f in files:
        arr = mpimg.imread(f)
        images.append(arr)

    return images
