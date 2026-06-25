"""
Entry point for RadStack Annotator.

Usage:
    python run.py                  # opens the default images/ folder
    python run.py /path/to/images  # opens a custom folder directly
"""

import os
import sys

from src.viewer import ImageStackViewer


def main():
    if len(sys.argv) > 1:
        data_path = sys.argv[1]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
        data_path = os.path.join(base, 'images')
    ImageStackViewer(data_path)


if __name__ == '__main__':
    main()
