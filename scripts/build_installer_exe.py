"""
Build script for the download-based installer using PyInstaller.

Produces a single-file installer exe that downloads the application zip from
the latest GitHub Release at install time (see scripts/download_installer.py).

Usage:
    python scripts/build_installer_exe.py

Paths are resolved from this file's location, so it works from any working
directory (local dev or a CI runner).
"""

import sys
import PyInstaller.__main__
from pathlib import Path

# Resolve project layout from this file, not the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_installer():
    """Build the download-based installer executable."""
    installer_script = PROJECT_ROOT / "scripts" / "download_installer.py"
    icon_path = PROJECT_ROOT / "src" / "icons" / "sorterIcon.ico"

    if not installer_script.exists():
        print(f"Error: Installer script not found at {installer_script}")
        sys.exit(1)

    print("Building download-based installer...")
    print(f"Installer script: {installer_script}")
    print(f"Output directory: {PROJECT_ROOT / 'dist'}")

    # PyInstaller arguments
    args = [
        "--name=OCR_File_Sorter_Download_Installer",
        "--onefile",
        "--noconsole",
        f"--distpath={PROJECT_ROOT / 'dist'}",
        f"--workpath={PROJECT_ROOT / 'build' / 'download_installer'}",
        f"--specpath={PROJECT_ROOT / 'build' / 'download_installer'}",
        "--hidden-import=tkinter",
        "--hidden-import=urllib.request",
        "--hidden-import=winreg",
        "--clean",
        "--noconfirm",
    ]

    if icon_path.exists():
        args.extend(["--icon", str(icon_path)])
    else:
        print(f"Warning: Icon file not found at {icon_path}")

    args.append(str(installer_script))

    try:
        PyInstaller.__main__.run(args)
        out = PROJECT_ROOT / "dist" / "OCR_File_Sorter_Download_Installer.exe"
        print("\n" + "=" * 50)
        print("Installer build completed successfully!")
        print(f"Installer location: {out}")
        print("=" * 50)
    except Exception as e:
        print(f"Installer build failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    build_installer()
