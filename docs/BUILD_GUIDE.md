# Ghost - Build Guide

## Overview

This guide explains how to build the Ghost application into a standalone executable using PyInstaller.

## Prerequisites

### 1. Install PyInstaller
```bash
pip install pyinstaller
```

### 2. Verify All Dependencies
Make sure all packages are installed:
```bash
pip install -r requirements.txt
```

### 3. Check Icon File
Verify the icon exists:
```bash
dir icons\logo-main.png
```

## Building the Application

### Method 1: Using the Spec File (Recommended)

The `main.spec` file is pre-configured with all necessary settings.

**Build command:**
```bash
pyinstaller main.spec
```

This will:
- ✅ Use the configured spec file
- ✅ Include all dependencies
- ✅ Bundle the icons folder
- ✅ Include Firebase config files
- ✅ Set the app icon
- ✅ Create a single executable

**Output:**
- Executable: `dist/Ghost.exe`
- Build files: `build/` folder

### Method 2: From Scratch (If spec file is missing)

Generate a new spec file:
```bash
pyinstaller --name="Ghost" --windowed --onefile --icon="icons/logo-main.png" main.py
```

Then edit the generated `Ghost.spec` file to match `main.spec` configuration.

## Build Options

### Debug Build (With Console)

For debugging, you may want to see console output:

1. Open `main.spec`
2. Change line 163:
   ```python
   console=True,  # Set to True for debugging
   ```
3. Build:
   ```bash
   pyinstaller main.spec
   ```

This will show a console window with print statements and errors.

### Release Build (No Console)

For production release:

1. Open `main.spec`
2. Ensure line 163:
   ```python
   console=False,  # Set to False for release
   ```
3. Build:
   ```bash
   pyinstaller main.spec
   ```

This creates a clean GUI application without console window.

## What Gets Included

### Data Files
- ✅ `icons/` folder (app icon and logo)
- ✅ `firebase_config.json` (if exists)
- ✅ `github_config.json` (if exists)
- ✅ Google Generative AI data files
- ✅ Firebase Admin SDK data files
- ✅ Anthropic data files

### Python Packages
All required packages are bundled:
- PyQt6 (GUI framework)
- Firebase Admin SDK (Firestore)
- Google Generative AI (Gemini)
- Anthropic (Claude)
- PyGithub (GitHub integration)
- OpenCV (video processing)
- Pillow (image processing)
- And all dependencies...

### Hidden Imports
The spec file includes all necessary hidden imports that PyInstaller might miss.

## Build Process Explained

### Step 1: Analysis
PyInstaller analyzes `main.py` and finds all imports.

### Step 2: Collecting Files
- Copies Python files
- Includes data files (icons, configs)
- Collects package data

### Step 3: Bundling
- Compresses Python code
- Creates bootloader
- Packages everything together

### Step 4: Executable Creation
- Creates `Ghost.exe` in `dist/` folder
- Sets icon
- Configures as windowed app (no console)

## After Building

### Testing the Executable

1. **Navigate to dist folder:**
   ```bash
   cd dist
   ```

2. **Run the executable:**
   ```bash
   Ghost.exe
   ```

3. **Check functionality:**
   - [ ] App window opens
   - [ ] Icon displays correctly
   - [ ] Logo shows beside "Ghost" title
   - [ ] All tabs work (Chat, History, Settings, etc.)
   - [ ] Firebase authentication works
   - [ ] Chat history loads
   - [ ] No console errors (if console=False)

### Distributing the Application

The `dist/Ghost.exe` file is standalone and can be distributed. Users just need:
- Windows 10/11
- No Python installation required
- No dependencies required

**Distribution options:**
1. Direct download (share the .exe file)
2. Installer creation (use Inno Setup or NSIS)
3. Portable version (zip file with exe + config)

## Troubleshooting

### Build Fails: "Module not found"

**Problem:** PyInstaller can't find a module.

**Solution:** Add to `hiddenimports` in `main.spec`:
```python
hiddenimports = [
    # ... existing imports ...
    'your_missing_module',
]
```

### Build Succeeds but App Crashes

**Problem:** Missing runtime data files.

**Solution 1:** Build with console to see error:
```python
console=True,  # in main.spec line 163
```

**Solution 2:** Add missing data files to `datas`:
```python
datas += [('path/to/file', 'destination')]
```

### Icon Not Showing

**Problem:** Icon path incorrect or file missing.

**Solution:** Verify:
```bash
dir icons\logo-main.png
```

If missing, the build will succeed but use default icon.

### Large Executable Size

**Problem:** `Ghost.exe` is very large (300MB+).

**Causes:**
- Many dependencies bundled
- OpenCV and numpy are large
- Firebase libraries are large

**Optimizations:**
1. Exclude unused packages in `main.spec`:
   ```python
   excludes=[
       'unused_package',
   ]
   ```

2. Use UPX compression (already enabled):
   ```python
   upx=True,
   ```

3. Consider removing optional features if size is critical

### App Runs Slowly on First Start

**Normal behavior:**
- First launch extracts files
- Subsequent launches are faster
- Firebase/Google SDK initialization takes time

### Config Files Not Found

**Problem:** App can't find `firebase_config.json`.

**Solution:** Place config files in same directory as `Ghost.exe`:
```
dist/
├── Ghost.exe
├── firebase_config.json
├── github_config.json
```

Or ensure they're bundled correctly in `main.spec`:
```python
if os.path.exists('firebase_config.json'):
    datas += [('firebase_config.json', '.')]
```

## Advanced Configuration

### Custom Build Location

To change output directory:
```bash
pyinstaller main.spec --distpath custom_dist
```

### Clean Build

Remove old build artifacts:
```bash
# Windows
rmdir /s /q build dist
del Ghost.spec

# Then rebuild
pyinstaller main.spec
```

### Build for Different Architecture

For 32-bit Windows:
```bash
pyinstaller main.spec --target-arch=x86
```

(Requires 32-bit Python installation)

## Build Script

Create `build.bat` for easy building:

```batch
@echo off
echo Building Ghost application...
echo.

REM Clean old builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build
pyinstaller main.spec

REM Check success
if exist dist\Ghost.exe (
    echo.
    echo ✅ Build successful!
    echo Executable: dist\Ghost.exe
    echo.
    pause
) else (
    echo.
    echo ❌ Build failed!
    echo Check error messages above.
    echo.
    pause
)
```

Run with:
```bash
build.bat
```

## Continuous Integration

For automated builds, create `.github/workflows/build.yml`:

```yaml
name: Build Ghost

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: windows-latest

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.12'

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pyinstaller

    - name: Build with PyInstaller
      run: pyinstaller main.spec

    - name: Upload artifact
      uses: actions/upload-artifact@v2
      with:
        name: Ghost-Windows
        path: dist/Ghost.exe
```

## Performance Tips

### Faster Builds

1. **Use spec file** (don't regenerate each time)
2. **Keep build folder** between builds (PyInstaller caches)
3. **Exclude unnecessary packages**
4. **Use SSD** for faster I/O

### Smaller Executables

1. **Enable UPX compression** (already enabled)
2. **Exclude test/dev packages**
3. **Remove unused imports from code**
4. **Consider splitting into multiple executables** if very large

## Versioning

Add version info to the executable:

1. Create `version.txt`:
```
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0),
    prodvers=(1, 0, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'Your Company'),
        StringStruct('FileDescription', 'Ghost - AI Assistant'),
        StringStruct('FileVersion', '1.0.0.0'),
        StringStruct('ProductName', 'Ghost'),
        StringStruct('ProductVersion', '1.0.0.0')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
```

2. Add to `main.spec`:
```python
exe = EXE(
    # ... existing code ...
    version='version.txt',
)
```

## Checklist Before Building

- [ ] All dependencies installed (`pip list`)
- [ ] Icon file exists (`icons/logo-main.png`)
- [ ] Firebase config present (if using Firebase)
- [ ] Code tested and working
- [ ] Console setting correct (False for release)
- [ ] Spec file up to date
- [ ] Previous build cleaned (optional)

## Post-Build Checklist

- [ ] Executable created successfully
- [ ] App launches without errors
- [ ] All features work
- [ ] Icon displays correctly
- [ ] Config files loaded
- [ ] No antivirus false positives
- [ ] File size reasonable
- [ ] Performance acceptable

## Support

For issues:
1. Check error messages in console build
2. Verify all files are included in spec
3. Test with clean Python environment
4. Check PyInstaller documentation: https://pyinstaller.org/

## Summary

**Quick Build:**
```bash
pyinstaller main.spec
```

**Output:**
```
dist/Ghost.exe  ← Your standalone application
```

**Distribution:**
- Share `Ghost.exe` directly
- Or create installer with Inno Setup
- No Python required for end users

**That's it! You're ready to build Ghost! 🎉**
