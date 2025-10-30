@echo off
REM Ghost Build Script
REM Builds the Ghost application using PyInstaller

echo ========================================
echo    Ghost Application Builder
echo ========================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed!
    echo Please install it with: pip install pyinstaller
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking prerequisites...
echo.

REM Check if main.spec exists
if not exist main.spec (
    echo [ERROR] main.spec file not found!
    echo.
    pause
    exit /b 1
)

REM Check if icons folder exists
if not exist icons\logo-main.png (
    echo [WARNING] Icon file not found: icons\logo-main.png
    echo Build will continue but icon may not display correctly.
    echo.
)

echo [2/4] Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo    - Removed old build artifacts
echo.

echo [3/4] Building Ghost application...
echo    This may take 5-10 minutes on first build...
echo.

REM Build with PyInstaller
pyinstaller main.spec

REM Check if build succeeded
if not exist dist\Ghost.exe (
    echo.
    echo ========================================
    echo [FAILED] Build failed!
    echo ========================================
    echo.
    echo Check error messages above for details.
    echo.
    echo Common fixes:
    echo - Install missing packages: pip install -r requirements.txt
    echo - Check Python version (3.10+ required)
    echo - Verify all imports in main.py
    echo.
    pause
    exit /b 1
)

echo.
echo [4/4] Build complete!
echo.

REM Get file size
for %%A in (dist\Ghost.exe) do set size=%%~zA
set /a size_mb=%size:~0,-6%
if "%size_mb%"=="" set size_mb=0

echo ========================================
echo   Build Successful!
echo ========================================
echo.
echo Executable: dist\Ghost.exe
echo File size: ~%size_mb% MB
echo.
echo Next steps:
echo   1. Test: dist\Ghost.exe
echo   2. Distribute: Share the Ghost.exe file
echo   3. No Python needed for end users!
echo.

REM Offer to run the executable
set /p run="Do you want to run Ghost.exe now? (Y/N): "
if /i "%run%"=="Y" (
    echo.
    echo Launching Ghost...
    start "" "dist\Ghost.exe"
)

echo.
echo ========================================
echo Press any key to exit...
pause >nul
