"""
Build script for OCR File Sorter executable using PyInstaller.

Creates a standalone Windows build with all necessary dependencies.

Usage:
    python scripts/build_exe.py          # release build (windowed, no console)
    python scripts/build_exe.py debug    # debug build (console enabled for tracebacks)

Paths are resolved from this file's location, so the script works from any
working directory (local dev or a CI runner).
"""

import re
import sys
import PyInstaller.__main__
from pathlib import Path

# Resolve project layout from this file, not the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"


def get_version():
    """Read __version__ from src/__init__.py (single source of truth)."""
    init_file = SRC / "__init__.py"
    match = re.search(
        r'__version__\s*=\s*["\']([^"\']+)["\']',
        init_file.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else "0.0.0"


def build_executable(debug=False):
    """Build the executable using PyInstaller with all necessary options."""
    main_script = SRC / "main.py"
    icon_path = SRC / "icons" / "sorterIcon.ico"

    if not main_script.exists():
        print(f"Error: Main script not found at {main_script}")
        sys.exit(1)

    version = get_version()
    app_name = "OCR File Sorter Debug" if debug else "OCR File Sorter"
    build_kind = "debug" if debug else "release"

    print(f"Building {app_name} v{version} ({build_kind})...")
    print(f"Main script: {main_script}")
    print(f"Output directory: {PROJECT_ROOT / 'dist' / app_name}")

    # PyInstaller arguments
    args = [
        f"--name={app_name}",
        # Directory mode (faster startup, smaller installer than --onefile).
        # Release hides the console; debug keeps it so tracebacks are visible.
        "--console" if debug else "--noconsole",
        f"--distpath={PROJECT_ROOT / 'dist'}",
        f"--workpath={PROJECT_ROOT / 'build'}",
        f"--specpath={PROJECT_ROOT / 'build'}",
        # Ensure `from src.ui_qt import app` resolves during analysis.
        f"--paths={PROJECT_ROOT}",
        # Add data files.
        f"--add-data={SRC / 'icons' / '*'};src/icons",
        f"--add-data={SRC / 'mappings' / 'example.json'};src/mappings",
        f"--add-data={SRC / 'mappings' / 'example_template'};src/mappings/example_template",
        # Hidden imports that PyInstaller may miss.
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=PIL",
        "--hidden-import=fitz",
        "--hidden-import=pymupdf",
        "--hidden-import=pytesseract",
        # The app uses only QtCore/QtGui/QtWidgets; skip the heavy Qt extras
        # (WebEngine, QML, 3D…) that PySide6 would otherwise pull in.
        "--exclude-module=PySide6.QtWebEngineCore",
        "--exclude-module=PySide6.QtWebEngineWidgets",
        "--exclude-module=PySide6.QtQml",
        "--exclude-module=PySide6.QtQuick",
        "--exclude-module=PySide6.QtQuickWidgets",
        "--exclude-module=PySide6.Qt3DCore",
        "--exclude-module=PySide6.Qt3DRender",
        "--exclude-module=PySide6.QtCharts",
        "--exclude-module=PySide6.QtDataVisualization",
        "--exclude-module=PySide6.QtMultimedia",
        "--exclude-module=PySide6.QtNetwork",
        "--exclude-module=PySide6.QtOpenGL",
        "--exclude-module=PySide6.QtPdf",
        "--exclude-module=PySide6.QtSql",
        "--exclude-module=PySide6.QtTest",
        "--exclude-module=tkinter",
        # More selective PyMuPDF inclusion (avoid dev files).
        "--collect-submodules=fitz",
        "--collect-submodules=pymupdf",
        "--copy-metadata=pymupdf",
        "--collect-binaries=pymupdf",
        "--exclude-module=pymupdf.mupdf-devel",
        # Clean build, no interactive prompts (safe for CI).
        "--clean",
        "--noconfirm",
    ]

    if debug:
        args.append("--debug=noarchive")

    if icon_path.exists():
        args.extend(["--icon", str(icon_path)])
    else:
        print(f"Warning: Icon file not found at {icon_path}")

    args.append(str(main_script))

    try:
        PyInstaller.__main__.run(args)
        out_dir = PROJECT_ROOT / "dist" / app_name
        print("\n" + "=" * 50)
        print("Build completed successfully!")
        print(f"Executable location: {out_dir / (app_name + '.exe')}")
        print("=" * 50)
    except Exception as e:
        print(f"Build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    is_debug = len(sys.argv) > 1 and sys.argv[1].lower() == "debug"
    build_executable(debug=is_debug)
