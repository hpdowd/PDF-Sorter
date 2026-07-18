"""
Download-based installer for OCR File Sorter
Instead of embedding the app, this installer downloads it from a URL.
This approach reduces installer size dramatically and enables easier updates.
"""

import os
import sys
import subprocess
import tempfile
import zipfile
import shutil
import urllib.request
import urllib.parse
import json
from pathlib import Path
import winreg
import tkinter as tk
from tkinter import messagebox, ttk
import threading
import time

class DownloadBasedInstaller:
    """Installer that downloads the application from a URL."""
    
    def __init__(self):
        # Default installation to a more user-friendly location
        self.install_dir = Path.home() / "AppData" / "Local" / "Programs"
        self.tesseract_url = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.3.3.20231005/tesseract-ocr-w64-setup-5.3.3.20231005.exe"
        
        # Configuration for download URLs
        self.app_config = {
            # GitHub releases approach.
            # NOTE: github_repo must be the GitHub *mirror* slug (owner/name).
            "github_repo": "hpdowd/PDF-Sorter",
            "release_tag": "latest",  # Always fetch the newest published release

            # Direct download URLs (primary)
            "app_zip_url": "https://github.com/hpdowd/PDF-Sorter/releases/latest/download/OCR_File_Sorter.zip",
            "fallback_url": "https://github.com/hpdowd/PDF-Sorter/releases/latest/download/OCR_File_Sorter.zip",
            
            # Local file paths for testing (ENABLED for now)
            "local_zip_path": str(Path(__file__).parent.parent / "dist" / "OCR_File_Sorter.zip"),
        }
        
        self.progress_var = None
        self.status_var = None
        self.root = None
        
    def get_download_url(self):
        """Get the download URL for the application."""
        
        # Option 1: Use local file for testing
        if self.app_config.get("local_zip_path"):
            local_path = Path(self.app_config["local_zip_path"])
            if local_path.exists():
                return f"file:///{local_path.as_posix()}"
        
        # Option 2: GitHub releases API
        try:
            if self.app_config.get("github_repo"):
                repo = self.app_config["github_repo"]
                if self.app_config["release_tag"] == "latest":
                    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
                else:
                    api_url = f"https://api.github.com/repos/{repo}/releases/tags/{self.app_config['release_tag']}"
                
                # Get release info
                with urllib.request.urlopen(api_url) as response:
                    release_data = json.loads(response.read().decode())
                
                # Find the app zip in assets
                for asset in release_data.get("assets", []):
                    if asset["name"].endswith(".zip") and "OCR_File_Sorter" in asset["name"]:
                        return asset["browser_download_url"]
        except Exception as e:
            print(f"GitHub API failed: {e}")
        
        # Option 3: Direct URL
        if self.app_config.get("app_zip_url"):
            return self.app_config["app_zip_url"]
        
        # Option 4: Fallback URL
        if self.app_config.get("fallback_url"):
            return self.app_config["fallback_url"]
        
        raise Exception("No valid download URL found for the application")
    
    def download_with_progress(self, url, destination, description="Downloading"):
        """Download a file with progress reporting."""
        
        def update_progress(block_count, block_size, total_size):
            if total_size > 0:
                progress = min(100, (block_count * block_size * 100) // total_size)
                if self.progress_var:
                    self.progress_var.set(progress)
                if self.status_var:
                    downloaded_mb = (block_count * block_size) / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    self.status_var.set(f"{description}: {downloaded_mb:.1f} MB / {total_mb:.1f} MB")
                if self.root:
                    self.root.update_idletasks()
        
        try:
            if self.status_var:
                self.status_var.set(f"Starting {description.lower()}...")
            
            # Handle file:// URLs for local testing
            if url.startswith("file:///"):
                local_path = url[8:]  # Remove "file:///" prefix
                shutil.copy2(local_path, destination)
                if self.progress_var:
                    self.progress_var.set(100)
                if self.status_var:
                    self.status_var.set(f"{description} completed")
                return True
            
            # Download from web
            urllib.request.urlretrieve(url, destination, update_progress)
            return True
            
        except Exception as e:
            if self.status_var:
                self.status_var.set(f"Failed to download: {e}")
            return False
    
    def install_application(self):
        """Download and install the main application."""
        try:
            # Get download URL
            download_url = self.get_download_url()
            
            # Create temporary download location
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
                temp_zip_path = temp_file.name
            
            # Download the application zip
            if not self.download_with_progress(download_url, temp_zip_path, "Downloading OCR File Sorter"):
                return False
            
            if self.status_var:
                self.status_var.set("Extracting application...")
            if self.progress_var:
                self.progress_var.set(50)
            
            # Create the base install directory (user-specified path)
            base_install_dir = Path(self.dir_var.get()) if hasattr(self, 'dir_var') else self.install_dir
            base_install_dir.mkdir(parents=True, exist_ok=True)
            
            # Create the actual application folder inside the base directory
            app_install_dir = base_install_dir / "OCR File Sorter"
            app_install_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract to the application directory
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(app_install_dir)
            
            # Update the install_dir for other methods to use
            self.install_dir = app_install_dir
            
            # Clean up temp file
            os.unlink(temp_zip_path)
            
            if self.status_var:
                self.status_var.set("Creating shortcuts...")
            if self.progress_var:
                self.progress_var.set(75)
            
            # Create desktop shortcut
            self.create_desktop_shortcut()
            
            if self.status_var:
                self.status_var.set("Installation completed successfully!")
            if self.progress_var:
                self.progress_var.set(100)
            
            return True
            
        except Exception as e:
            if self.status_var:
                self.status_var.set(f"Installation failed: {e}")
            return False
    
    def create_zip_for_download(self, app_directory, output_zip):
        """Helper method to create a zip file from the built application directory."""
        
        print(f"Creating downloadable zip: {output_zip}")
        
        app_path = Path(app_directory)
        if not app_path.exists():
            raise Exception(f"Application directory not found: {app_directory}")
        
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in app_path.rglob('*'):
                if file_path.is_file():
                    # Create relative path for zip
                    arcname = file_path.relative_to(app_path)
                    zipf.write(file_path, arcname)
        
        print(f"Zip created: {Path(output_zip).stat().st_size / (1024*1024):.1f} MB")
        return output_zip
    
    def create_desktop_shortcut(self):
        """Create a desktop shortcut for the application."""
        try:
            import win32com.client
            
            # Get desktop path
            desktop = Path.home() / "Desktop"
            shortcut_path = desktop / "OCR File Sorter.lnk"
            
            # Get the executable path
            exe_path = self.install_dir / "OCR File Sorter.exe"
            
            if not exe_path.exists():
                print(f"Warning: Executable not found at {exe_path}")
                return False
            
            # Create shortcut
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(str(shortcut_path))
            shortcut.Targetpath = str(exe_path)
            shortcut.WorkingDirectory = str(self.install_dir)
            shortcut.Description = "OCR File Sorter - Intelligent PDF sorting application"
            
            # Set icon if available
            icon_path = self.install_dir / "_internal" / "sorterIcon.ico"
            if icon_path.exists():
                shortcut.IconLocation = str(icon_path)
            
            shortcut.save()
            return True
            
        except ImportError:
            # Fallback: Create a simple batch file if win32com is not available
            try:
                desktop = Path.home() / "Desktop"
                batch_path = desktop / "OCR File Sorter.bat"
                exe_path = self.install_dir / "OCR File Sorter.exe"
                
                batch_content = f'''@echo off
cd /d "{self.install_dir}"
start "" "{exe_path}"
'''
                with open(batch_path, 'w') as f:
                    f.write(batch_content)
                return True
            except Exception as e:
                print(f"Failed to create desktop shortcut: {e}")
                return False
        except Exception as e:
            print(f"Failed to create desktop shortcut: {e}")
            return False
    
    def browse_directory(self):
        """Open a directory browser dialog."""
        from tkinter import filedialog
        
        initial_dir = self.dir_var.get() if hasattr(self, 'dir_var') else str(self.install_dir)
        selected_dir = filedialog.askdirectory(
            title="Select Installation Directory",
            initialdir=initial_dir
        )
        
        if selected_dir:
            self.dir_var.set(selected_dir)
    
    def create_gui(self):
        """Create the installer GUI."""
        self.root = tk.Tk()
        self.root.title("OCR File Sorter Installer")
        self.root.geometry("500x420")
        self.root.resizable(False, False)
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="OCR File Sorter Installer", 
                               font=('Segoe UI', 14, 'bold'))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Description
        desc_text = """This installer will download and set up OCR File Sorter:

• Downloads latest OCR File Sorter application
• Installs Tesseract OCR engine (user-specific)
• Creates desktop shortcuts and file associations
• Configures user PATH

Installation Directory:"""
        
        desc_label = ttk.Label(main_frame, text=desc_text, justify=tk.LEFT,
                               font=('Segoe UI', 9))
        desc_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        
        # Install directory
        dir_frame = ttk.Frame(main_frame)
        dir_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))
        
        self.dir_var = tk.StringVar(value=str(self.install_dir))
        dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var, width=50,
                             font=('Segoe UI', 9))
        dir_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        
        browse_btn = ttk.Button(dir_frame, text="Browse...", command=self.browse_directory)
        browse_btn.grid(row=0, column=1)
        
        dir_frame.columnconfigure(0, weight=1)
        
        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Installation Progress", padding="10")
        progress_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 20))
        
        self.progress_var = tk.IntVar()
        progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.status_var = tk.StringVar(value="Ready to install")
        status_label = ttk.Label(progress_frame, textvariable=self.status_var,
                                font=('Segoe UI', 8))
        status_label.grid(row=1, column=0, sticky=tk.W)
        
        progress_frame.columnconfigure(0, weight=1)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=(20, 0))
        
        install_btn = ttk.Button(button_frame, text="Install", command=self.start_installation,
                                style='Accent.TButton')
        install_btn.grid(row=0, column=0, padx=(0, 10))
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.root.quit)
        cancel_btn.grid(row=0, column=1)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
    
    def start_installation(self):
        """Start the installation process in a separate thread."""
        def install_thread():
            self.install_application()
        
        thread = threading.Thread(target=install_thread)
        thread.daemon = True
        thread.start()
    
    def run(self):
        """Run the installer."""
        self.create_gui()
        self.root.mainloop()

def create_downloadable_zip():
    """Create a zip file from the built application for download distribution."""
    
    # Paths
    current_dir = Path.cwd().parent
    app_dir = current_dir / "dist" / "OCR File Sorter"
    output_zip = current_dir / "dist" / "OCR_File_Sorter.zip"
    
    if not app_dir.exists():
        print("Error: Built application directory not found.")
        print("Please run the build process first.")
        return None
    
    installer = DownloadBasedInstaller()
    return installer.create_zip_for_download(app_dir, output_zip)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "create-zip":
        # Create downloadable zip
        create_downloadable_zip()
    else:
        # Run installer
        installer = DownloadBasedInstaller()
        installer.run()
