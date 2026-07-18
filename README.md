# 📄 OCR File Sorter

A PDF sorting application that automatically organizes documents based on their content using their text or OCR.

## Quick Start

### For Users
1. Download the installer: `OCR_File_Sorter_Installer.exe`
2. Run the installer and follow the setup wizard
3. Start sorting your PDFs!

### For Developers
```bash
# Clone and setup
git clone https://git.henrydowd.dev/henry/PDF-Sorter.git
cd PDF-Sorter

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r config/requirements.txt

# Run the application
python src/main.py
```

## Project Structure

```
PDF-Sorter/
├── src/                    # Main application code
│   ├── main.py               # Application entry point
│   ├── gui.py                # User interface
│   ├── sorter.py             # Core sorting logic
│   ├── utils.py              # Utility functions
│   ├── icons/             # Application icons
│   ├── mappings/          # Sorting rule examples
│   └── mapping_editor/    # Mapping editor module
├── tests/                 # Test suite
│   ├── test_runner/       # PDF testing framework
│   └── ...                   # Unit and integration tests
├── scripts/               # Build and utility scripts
│   ├── build.bat            # Build the app + distribution zip
│   ├── build_installer.bat  # Build the download-based installer
│   ├── build_complete.bat   # Build both app and installer
│   ├── build_exe.py         # PyInstaller build script
│   └── build_installer_exe.py # Installer build script
├── config/                # Configuration files
│   ├── requirements.txt     # Runtime dependencies
│   ├── requirements-build.txt # Build dependencies
│   └── requirements-dev.txt # Development dependencies
├── docs/                  # Documentation
│   ├── BUILD_SYSTEM.md      # Build system overview
│   └── VERSIONING.md        # Versioning policy
├── build/                 # Build artifacts (ignored)
├── dist/                  # Distribution files
└── quick-build.bat           # Quick build convenience script
```

## Features

### **Intelligent PDF Processing**
- **Text Extraction**: Direct PDF text reading with OCR fallback
- **Pattern Matching**: Flexible phrase-based sorting rules
- **OCR Support**: Handles scanned documents with Tesseract
- **Robust Parsing**: Handles OCR quirks and text variations

### **Smart Sorting**
- **Custom Mappings**: Create your own sorting rules
- **Multiple Phrases**: One rule can match several phrases (separate with `|`)
- **Output Folder**: Choose where sorted files are filed
- **Preview & Undo**: Review the plan before sorting; copy or move; undo the last sort
- **Template System**: Predefined folder structures
- **Batch Processing**: Sort multiple files at once
- **File Naming**: Configurable output file naming schemes

### **User-Friendly Interface**
- **Drag & Drop**: Easy folder selection
- **Progress Tracking**: Real-time sorting progress
- **Preferences**: Set scan defaults from the File menu
- **CSV Export**: Save the sort preview for an audit trail
- **Persistent Logging**: Actions written to a per-user log file
- **Mapping Editor**: Built-in rule editor with drag-to-assign destinations

### **Professional Features**
- **Comprehensive Testing**: PDF testing framework included
- **Easy Distribution**: Single-file installer with dependencies
- **Cross-Platform**: Windows focus with portable codebase
- **Extensible**: Modular architecture for easy enhancement

## Building

### Quick Build
```bash
# Build everything (application + installer)
quick-build.bat
```

### Manual Build Steps
```bash
# 1. Install build dependencies
pip install -r config/requirements-build.txt

# 2. Build main application + distribution zip
cd scripts
python build_exe.py

# 3. Build the download installer (optional)
python build_installer_exe.py
```

### Output Files
- `dist/OCR File Sorter/OCR File Sorter.exe` - Main application
- `dist/OCR_File_Sorter.zip` - Application package (uploaded to releases)
- `dist/OCR_File_Sorter_Download_Installer.exe` - Download-based installer

## Testing

### Run Tests
```bash
# Run all tests
python -m pytest tests/

# Test PDF sorting specifically
cd tests/test_runner
python run_pdf_tests.py --verbose
```

### PDF Testing Framework
The included test runner lets you easily test PDF sorting:
1. Add PDFs to `tests/test_runner/input_pdfs/`
2. Add mapping files to `tests/test_runner/test_mappings/`
3. Run `run_pdf_tests.py` to see where each PDF would be sorted

## Requirements

### Runtime
- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.8+ (for source)
- **Dependencies**: See `config/requirements.txt`

### Optional
- **Tesseract OCR**: For scanned PDF support (auto-installed with installer)

## Use Cases

- **Document Management**: Organize invoices, contracts, reports
- **Office Automation**: Sort incoming documents by type
- **Archive Organization**: Clean up document collections
- **Workflow Integration**: Part of larger document processing pipelines

## License

This project is licensed under the terms specified in LICENCE.txt.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## Documentation

- [Build System](docs/BUILD_SYSTEM.md) - Build scripts and their outputs
- [Versioning Policy](docs/VERSIONING.md) - How releases are versioned and cut
- [Test Runner Guide](tests/test_runner/README.md) - PDF testing framework

## Support

- Check the documentation in the `docs/` folder
- Review test examples in `tests/test_runner/`
- Open an issue for bugs or feature requests

---

**Transform your document chaos into organized bliss!** 📄✨
