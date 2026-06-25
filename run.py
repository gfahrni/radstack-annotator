"""
Entry point for RadStack Annotator (PyQt6 edition).

Usage:
    python run.py                  # start with empty state
    python run.py /path/to/images  # open a folder directly
"""

import sys
import os
from PyQt6.QtWidgets import QApplication
from src.viewer import ImageStackViewer


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('RadStack Annotator')
    app.setOrganizationName('RadStack')

    data_path = sys.argv[1] if len(sys.argv) > 1 else None

    viewer = ImageStackViewer(data_path)
    viewer.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
