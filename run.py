"""
Entry point for RadStack Annotator.

This is the thin launch script. It handles command-line arguments,
resolves the data directory, and hands control to the ImageStackViewer class.

Usage:
    python run.py                  # opens ../images/ folder
    python run.py /path/to/images  # opens a custom folder
"""

import sys
import os
import json

from src.viewer import ImageStackViewer


def _default_data_path():
    settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    try:
        with open(settings_path) as f:
            settings = json.load(f)
        rel = settings.get('default_data_path', '../images')
    except (FileNotFoundError, json.JSONDecodeError):
        rel = '../images'

    return os.path.join(os.path.dirname(__file__), rel)


def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else _default_data_path()

    if not os.path.isdir(data_path):
        print(f'Error: {data_path} is not a valid directory.')
        sys.exit(1)

    ImageStackViewer(data_path)


if __name__ == '__main__':
    main()
