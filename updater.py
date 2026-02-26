"""
Auto-updater for Ghost Widget
Checks for updates from GitHub releases and handles download/installation
"""

import requests
import json
import os
import sys
import subprocess
import tempfile
import hashlib
from pathlib import Path
from packaging import version as version_parser
from typing import Optional, Dict, Any, Callable

try:
    from version import __version__, UPDATE_CHECK_URL, GITHUB_REPO
except ImportError:
    __version__ = "1.0.0"
    UPDATE_CHECK_URL = "https://api.github.com/repos/not-ekalabya/ghost-widget/releases/latest"
    GITHUB_REPO = "not-ekalabya/ghost-widget"


class UpdateChecker:
    """Handles checking for and installing updates from GitHub releases"""

    def __init__(self, current_version: str = __version__, github_token: Optional[str] = None):
        """
        Initialize update checker

        Args:
            current_version: Current version of the application
            github_token: Optional GitHub personal access token for private repos
        """
        self.current_version = current_version
        self.update_url = UPDATE_CHECK_URL
        self.github_repo = GITHUB_REPO
        self.github_token = os.environ.get("GITHUB_TOKEN")
        if not self.github_token:
            print("[WARNING] GITHUB_TOKEN not set in environment. Private repo updates will not work.")
        self.download_progress_callback: Optional[Callable] = None

        # Setup logging to file
        self.log_file = Path(tempfile.gettempdir()) / "ghost_widget_update.log"
        self._init_logging()

    def _init_logging(self):
        """Initialize file logging for updates"""
        import logging

        # Create logger
        self.logger = logging.getLogger('GhostUpdater')
        self.logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        self.logger.handlers = []

        # File handler
        try:
            fh = logging.FileHandler(self.log_file, mode='a', encoding='utf-8')
            fh.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

            self.logger.info("=" * 60)
            self.logger.info("Update session started")
            self.logger.info(f"Current version: {self.current_version}")
            self.logger.info(f"Log file: {self.log_file}")
        except Exception as e:
            print(f"Failed to initialize logging: {e}")

    def _log(self, level: str, message: str):
        """Log message to both console and file"""
        print(message)
        if hasattr(self, 'logger'):
            getattr(self.logger, level.lower())(message)

    def check_for_updates(self, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Check if a new version is available on GitHub releases

        Args:
            timeout: Request timeout in seconds

        Returns:
            Dictionary with update info if available, None otherwise
            {
                'available': bool,
                'version': str,
                'download_url': str,
                'changelog': str,
                'published_at': str,
                'asset_name': str,
                'asset_size': int
            }
        """
        try:
            print(f"🔍 Checking for updates... (Current version: {self.current_version})")

            # Make request to GitHub API
            headers = {'Accept': 'application/json'}

            # Add authentication header if token is provided (for private repos)
            if self.github_token:
                headers['Authorization'] = f'token {self.github_token}'

            response = requests.get(self.update_url, headers=headers, timeout=timeout)

            if response.status_code != 200:
                error_msg = f"⚠️ Failed to check for updates: HTTP {response.status_code}"

                # Provide helpful messages for common errors
                if response.status_code == 404:
                    try:
                        error_data = response.json()
                        if 'message' in error_data and 'Not Found' in error_data['message']:
                            error_msg += "\n💡 No releases found. Please create a release on GitHub:"
                            error_msg += f"\n   1. Go to https://github.com/{self.github_repo}/releases/new"
                            error_msg += f"\n   2. Tag version: v{self.current_version}"
                            error_msg += "\n   3. Upload Ghost.exe as an asset"
                            error_msg += "\n   4. Publish the release"
                    except:
                        pass
                elif response.status_code == 403:
                    error_msg += "\n💡 GitHub API rate limit exceeded or invalid token"
                elif response.status_code == 401:
                    error_msg += "\n💡 Invalid GitHub token. Check updater.py line 39"

                print(error_msg)
                return None

            release_data = response.json()

            # Extract version from tag (remove 'v' prefix if present)
            latest_version = release_data['tag_name'].lstrip('v')

            # Compare versions
            is_newer = self._is_newer_version(latest_version, self.current_version)

            if not is_newer:
                print(f"✓ You're running the latest version ({self.current_version})")
                return {
                    'available': False,
                    'version': latest_version,
                    'current_version': self.current_version
                }

            # Find the Windows executable asset
            download_url = None
            asset_name = None
            asset_size = 0

            for asset in release_data.get('assets', []):
                if asset['name'].endswith('.exe'):
                    # Use API URL for private repos (works with token auth)
                    # browser_download_url only works in browser for private repos
                    download_url = asset['url']
                    asset_name = asset['name']
                    asset_size = asset['size']
                    break

            if not download_url:
                print("⚠️ No Windows executable found in release assets")
                return None

            print(f"✨ New version available: {latest_version} (Current: {self.current_version})")

            return {
                'available': True,
                'version': latest_version,
                'current_version': self.current_version,
                'download_url': download_url,
                'changelog': release_data.get('body', 'No changelog available'),
                'published_at': release_data.get('published_at', ''),
                'asset_name': asset_name,
                'asset_size': asset_size,
                'release_url': release_data.get('html_url', '')
            }

        except requests.RequestException as e:
            print(f"⚠️ Network error while checking for updates: {e}")
            return None
        except Exception as e:
            print(f"⚠️ Error checking for updates: {e}")
            return None

    def _is_newer_version(self, latest: str, current: str) -> bool:
        """
        Compare version strings to determine if latest is newer

        Args:
            latest: Latest version string
            current: Current version string

        Returns:
            True if latest is newer than current
        """
        try:
            return version_parser.parse(latest) > version_parser.parse(current)
        except Exception as e:
            print(f"⚠️ Error comparing versions: {e}")
            # Fallback to simple string comparison
            return latest > current

    def download_update(self, download_url: str, filename: str = None, progress_callback: Optional[Callable] = None) -> Optional[str]:
        """
        Download update from URL

        Args:
            download_url: URL to download the update from
            filename: Optional filename to save as (if None, will try to extract from response)
            progress_callback: Optional callback(downloaded_bytes, total_bytes) for progress updates

        Returns:
            Path to downloaded file, or None if failed
        """
        try:
            self._log("info", f"📥 Downloading update from: {download_url}")

            # Create temp directory for download
            temp_dir = Path(tempfile.gettempdir()) / "ghost_updates"
            temp_dir.mkdir(exist_ok=True)

            # Use provided filename or extract from Content-Disposition header
            if not filename:
                filename = download_url.split('/')[-1]

            download_path = temp_dir / filename

            self._log("info", f"Download destination: {download_path}")
            self._log("info", f"Filename: {filename}")

            # Prepare headers with authentication for private repos
            headers = {'Accept': 'application/octet-stream'}
            if self.github_token:
                headers['Authorization'] = f'token {self.github_token}'

            # Download with progress tracking
            response = requests.get(download_url, headers=headers, stream=True, timeout=300)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            self._log("info", f"📦 Total file size: {total_size / 1024 / 1024:.2f} MB" if total_size > 0 else "📦 File size unknown, downloading...")

            with open(download_path, 'wb') as f:
                chunk_count = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        chunk_count += 1

                        # Report progress every 100 chunks (roughly every 800KB) or if we have total_size
                        if progress_callback and (chunk_count % 100 == 0 or total_size > 0):
                            progress_callback(downloaded_size, total_size if total_size > 0 else downloaded_size)

            # Final progress update to ensure 100%
            if progress_callback:
                final_size = total_size if total_size > 0 else downloaded_size
                progress_callback(downloaded_size, final_size)

            self._log("info", f"✓ Update downloaded to: {download_path}")
            self._log("info", f"✓ Downloaded size: {downloaded_size / 1024 / 1024:.2f} MB")

            # Verify the download
            if not download_path.exists():
                self._log("error", "❌ Downloaded file not found after download!")
                return None

            actual_size = download_path.stat().st_size
            self._log("info", f"✓ File verification: {actual_size} bytes on disk")

            if total_size > 0 and actual_size != total_size:
                self._log("warning", f"⚠️  Warning: File size mismatch! Expected {total_size}, got {actual_size}")

            # Basic validation - check if it's a valid PE file (Windows executable)
            try:
                with open(download_path, 'rb') as f:
                    header = f.read(2)
                    if header != b'MZ':
                        self._log("error", "❌ Downloaded file is not a valid Windows executable!")
                        return None
                self._log("info", "✓ File format validation passed")
            except Exception as e:
                self._log("warning", f"⚠️  Could not validate file format: {e}")

            # DEBUGGING: Save a backup copy to inspect
            backup_path = download_path.parent / f"Ghost_backup_{downloaded_size}.exe"
            try:
                import shutil
                shutil.copy2(download_path, backup_path)
                self._log("info", f"🔍 DEBUG: Backup saved to: {backup_path}")
                self._log("info", f"   You can test this file manually to verify it works")
            except Exception as e:
                self._log("warning", f"⚠️  Could not create backup: {e}")

            return str(download_path)

        except Exception as e:
            self._log("error", f"❌ Error downloading update: {e}")
            import traceback
            self._log("error", traceback.format_exc())
            return None

    def install_update(self, installer_path: str, silent: bool = True) -> bool:
        """
        Save the downloaded update to the current directory

        Args:
            installer_path: Path to the downloaded installer (in temp folder)
            silent: Not used, kept for compatibility

        Returns:
            True if file was saved successfully
        """
        try:
            if not os.path.exists(installer_path):
                self._log("error", f"❌ Downloaded file not found: {installer_path}")
                return False

            self._log("info", f"💾 Saving update to current directory...")
            self._log("info", f"   Source: {installer_path}")
            self._log("info", f"   File size: {os.path.getsize(installer_path) / 1024 / 1024:.2f} MB")

            # Determine destination directory
            if getattr(sys, 'frozen', False):
                # Running as compiled executable - save next to the exe
                current_dir = os.path.dirname(os.path.abspath(sys.executable))
                current_exe = os.path.abspath(sys.executable)
            else:
                # Running in development mode - save in project root
                current_dir = os.getcwd()
                current_exe = None

            # Destination path - save as Ghost_new.exe to avoid file locking issues
            destination = os.path.join(current_dir, "Ghost_new.exe")

            self._log("info", f"   Current directory: {current_dir}")
            self._log("info", f"   Current exe: {current_exe}")
            self._log("info", f"   Destination: {destination}")

            # Check if destination directory exists and is writable
            if not os.path.exists(current_dir):
                self._log("error", f"❌ Destination directory does not exist: {current_dir}")
                return False

            if not os.access(current_dir, os.W_OK):
                self._log("error", f"❌ No write permission for directory: {current_dir}")
                return False

            # Remove old Ghost_new.exe if it exists
            if os.path.exists(destination):
                try:
                    os.remove(destination)
                    self._log("info", f"   Removed old Ghost_new.exe file")
                except Exception as e:
                    self._log("warning", f"⚠️  Could not remove old Ghost_new.exe: {e}")

            # Copy the file
            import shutil
            try:
                self._log("info", f"   Copying file...")
                shutil.copy2(installer_path, destination)
                self._log("info", f"✓ Update saved successfully!")
                self._log("info", f"   Location: {destination}")

                # Verify the file was copied
                if os.path.exists(destination):
                    copied_size = os.path.getsize(destination)
                    original_size = os.path.getsize(installer_path)

                    if copied_size == original_size:
                        self._log("info", f"✓ File verification passed ({copied_size} bytes)")
                        self._log("info", "✓ Update ready to install!")

                        # Store the paths for restart
                        self.update_ready = True
                        self.new_exe_path = destination
                        self.current_dir = current_dir
                        return True
                    else:
                        self._log("error", f"❌ File size mismatch after copy!")
                        self._log("error", f"   Expected: {original_size}, Got: {copied_size}")
                        return False
                else:
                    self._log("error", f"❌ File not found after copy: {destination}")
                    return False

            except Exception as e:
                self._log("error", f"❌ Failed to copy file: {e}")
                import traceback
                self._log("error", traceback.format_exc())
                return False

        except Exception as e:
            self._log("error", f"❌ Error saving update: {e}")
            import traceback
            self._log("error", traceback.format_exc())
            return False

    def apply_update_and_restart(self) -> bool:
        """
        Create a batch script to swap exe and restart, then exit the app
        This provides seamless one-click update experience
        """
        try:
            if not hasattr(self, 'update_ready') or not self.update_ready:
                self._log("error", "No update ready to apply")
                return False

            # Create minimal batch script for swap and restart
            batch_script = os.path.join(self.current_dir, "_update.bat")

            with open(batch_script, 'w') as f:
                f.write('@echo off\n')
                f.write('timeout /t 1 /nobreak >nul\n')  # Wait 1 second for app to close
                f.write(f'del /f /q "Ghost.exe" 2>nul\n')
                f.write(f'ren "Ghost_new.exe" "Ghost.exe"\n')
                f.write(f'start "" "Ghost.exe"\n')
                f.write(f'del /f /q "%~f0"\n')  # Delete the batch script itself

            self._log("info", f"✓ Created update script: {batch_script}")

            # Launch the batch script in detached mode
            import subprocess
            subprocess.Popen(
                [batch_script],
                cwd=self.current_dir,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                close_fds=True
            )

            self._log("info", "✓ Update script launched - app will restart momentarily")
            return True

        except Exception as e:
            self._log("error", f"❌ Failed to apply update: {e}")
            import traceback
            self._log("error", traceback.format_exc())
            return False

    def _create_restart_script(self, new_exe_path: str, current_exe_path: str) -> str:
        """
        Create a batch script to replace and restart the app after it closes

        Args:
            new_exe_path: Path to the new executable (Ghost_new.exe)
            current_exe_path: Path to the current running executable (Ghost.exe)

        Returns:
            Path to created batch script
        """
        try:
            # Create a temporary batch script
            temp_dir = Path(tempfile.gettempdir())
            script_path = temp_dir / "ghost_restart.bat"

            # Get the directory of the exe for working directory
            exe_dir = str(Path(current_exe_path).parent) if current_exe_path else str(Path(new_exe_path).parent)

            # Create log file for the script
            batch_log = str(temp_dir / "ghost_widget_restart.log")

            # Script that:
            # 1. Waits for Ghost.exe process to exit
            # 2. Replaces old Ghost.exe with new one
            # 3. Starts Ghost.exe
            # 4. Cleans up

            script_content = f"""@echo off
set LOGFILE={batch_log}

echo Ghost Widget Restart Script > "%LOGFILE%"
echo ============================== >> "%LOGFILE%"
echo Started at %DATE% %TIME% >> "%LOGFILE%"
echo New exe: {new_exe_path} >> "%LOGFILE%"
echo Current exe: {current_exe_path} >> "%LOGFILE%"
echo. >> "%LOGFILE%"

echo Waiting for Ghost to close...
echo Waiting for Ghost to close... >> "%LOGFILE%"

REM Wait for Ghost.exe to close
:WAIT_LOOP
timeout /t 1 /nobreak > nul
tasklist /FI "IMAGENAME eq Ghost.exe" 2>NUL | find /I /N "Ghost.exe">NUL
if "%ERRORLEVEL%"=="0" (
    goto WAIT_LOOP
)

echo Ghost closed at %TIME% >> "%LOGFILE%"
echo.

REM Wait for PyInstaller temp folders to be cleaned up
echo Waiting for cleanup (8 seconds)...
echo Waiting for PyInstaller cleanup... >> "%LOGFILE%"
timeout /t 8 /nobreak > nul

REM Clean up any orphaned _MEI folders from old PyInstaller extractions
echo Cleaning up old PyInstaller temp folders...
echo Cleaning up _MEI folders... >> "%LOGFILE%"
for /d %%G in ("%TEMP%\_MEI*") do (
    echo Removing: %%G >> "%LOGFILE%"
    rd /s /q "%%G" 2>nul
)
echo _MEI cleanup complete >> "%LOGFILE%"

REM Wait a bit more after cleanup
timeout /t 2 /nobreak > nul

echo Replacing Ghost.exe...
echo Replacing Ghost.exe... >> "%LOGFILE%"

REM Backup old version
if exist "{current_exe_path}" (
    if exist "{current_exe_path}.old" del /f /q "{current_exe_path}.old"
    move /y "{current_exe_path}" "{current_exe_path}.old" >> "%LOGFILE%" 2>&1
    echo Old version backed up >> "%LOGFILE%"
)

REM Move new version to replace old one
move /y "{new_exe_path}" "{current_exe_path}" >> "%LOGFILE%" 2>&1
echo New version moved to {current_exe_path} >> "%LOGFILE%"

REM Verify the new exe exists
if not exist "{current_exe_path}" (
    echo ERROR: Ghost.exe not found after move! >> "%LOGFILE%"
    echo Attempting to restore backup...
    if exist "{current_exe_path}.old" (
        move /y "{current_exe_path}.old" "{current_exe_path}"
        echo Backup restored >> "%LOGFILE%"
    )
    pause
    exit /b 1
)

echo Starting Ghost Widget...
echo Starting Ghost Widget... >> "%LOGFILE%"
echo Executable: {current_exe_path} >> "%LOGFILE%"
echo Working directory: {exe_dir} >> "%LOGFILE%"

cd /d "{exe_dir}"
start "" "{current_exe_path}"

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start Ghost Widget >> "%LOGFILE%"
    exit /b 1
)

echo Ghost Widget started successfully at %TIME% >> "%LOGFILE%"

REM Clean up backup and script after a delay
timeout /t 3 /nobreak > nul
if exist "{current_exe_path}.old" del /f /q "{current_exe_path}.old"
(goto) 2>nul & del /f /q "%~f0"
"""

            with open(script_path, 'w') as f:
                f.write(script_content)

            self._log("info", f"Restart script created: {script_path}")
            self._log("info", f"Restart log file: {batch_log}")

            return str(script_path)

        except Exception as e:
            self._log("error", f"Failed to create restart script: {e}")
            import traceback
            self._log("error", traceback.format_exc())
            return None

    def _create_update_script_DEPRECATED(self, new_exe_path: str, current_exe_path: str) -> str:
        """
        Create a batch script to replace the current executable

        Args:
            new_exe_path: Path to new executable
            current_exe_path: Path to current executable

        Returns:
            Path to created batch script
        """
        # Create a temporary batch script
        temp_dir = Path(tempfile.gettempdir())
        script_path = temp_dir / "ghost_update.bat"

        # Get the directory of the current exe for working directory
        current_exe_dir = str(Path(current_exe_path).parent)

        # Create log file for batch script
        batch_log = str(Path(tempfile.gettempdir()) / "ghost_widget_update_batch.log")

        # Batch script that:
        # 1. Waits for current process to exit
        # 2. Backs up old executable
        # 3. Copies new executable
        # 4. Restarts application
        # 5. Cleans up

        script_content = f"""@echo off
REM Log all output to file
set LOGFILE={batch_log}

echo Ghost Widget Update Installer > "%LOGFILE%"
echo ============================== >> "%LOGFILE%"
echo Update started at %DATE% %TIME% >> "%LOGFILE%"
echo. >> "%LOGFILE%"

title Ghost Widget Update Installer
color 0A
echo.
echo ========================================
echo   Ghost Widget Update Installer
echo ========================================
echo.
echo DO NOT CLOSE THIS WINDOW
echo Update in progress...
echo.
echo Source file: {new_exe_path}
echo Destination: {current_exe_path}
echo Log file: %LOGFILE%
echo.
echo DEBUG INFO: >> "%LOGFILE%"
echo Source: {new_exe_path} >> "%LOGFILE%"
echo Destination: {current_exe_path} >> "%LOGFILE%"
echo Working dir: {current_exe_dir} >> "%LOGFILE%"
echo.

echo [1/5] Waiting for Ghost to close...
echo [1/5] Waiting for Ghost to close... >> "%LOGFILE%"
timeout /t 3 /nobreak > nul

:WAIT_FOR_CLOSE
tasklist /FI "IMAGENAME eq Ghost.exe" 2>NUL | find /I /N "Ghost.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Ghost is still running, waiting...
    echo Ghost is still running, waiting... >> "%LOGFILE%"
    timeout /t 1 /nobreak > nul
    goto WAIT_FOR_CLOSE
)
echo Ghost closed successfully.
echo Ghost closed successfully at %TIME% >> "%LOGFILE%"
echo.

echo [2/5] Backing up current version...
echo [2/5] Backing up current version... >> "%LOGFILE%"
if exist "{current_exe_path}" (
    if exist "{current_exe_path}.old" (
        del /f /q "{current_exe_path}.old"
        echo Deleted old backup >> "%LOGFILE%"
    )
    move /y "{current_exe_path}" "{current_exe_path}.old" >> "%LOGFILE%" 2>&1

    REM Check if backup file exists instead of relying on ERRORLEVEL
    if not exist "{current_exe_path}.old" (
        echo ERROR: Failed to backup old version!
        echo ERROR: Backup file not found after move >> "%LOGFILE%"
        pause
        exit /b 1
    )
    if exist "{current_exe_path}" (
        echo ERROR: Failed to backup old version - original still exists!
        echo ERROR: Original file still exists after move >> "%LOGFILE%"
        pause
        exit /b 1
    )
    echo Backup created successfully.
    echo Backup created successfully >> "%LOGFILE%"
) else (
    echo No existing version found (first install).
    echo No existing version found (first install) >> "%LOGFILE%"
)
echo.

echo [3/5] Installing new version...
echo [3/5] Installing new version... >> "%LOGFILE%"
echo Source: {new_exe_path} >> "%LOGFILE%"
echo Destination: {current_exe_path} >> "%LOGFILE%"

REM List what's actually in the ghost_updates folder for debugging
echo.
echo Checking source file...
echo Files in ghost_updates folder: >> "%LOGFILE%"
dir /b "%TEMP%\ghost_updates" >> "%LOGFILE%" 2>&1
dir "%TEMP%\ghost_updates"

echo.
echo Checking paths...
echo Checking if source exists: {new_exe_path}
if exist "{new_exe_path}" (
    echo [OK] Source file EXISTS
    echo Source file EXISTS >> "%LOGFILE%"
    dir "{new_exe_path}" >> "%LOGFILE%"
    for %%I in ("{new_exe_path}") do echo Source size: %%~zI bytes
) else (
    echo [ERROR] Source file NOT FOUND!
    echo ERROR: Update file not found at {new_exe_path}
    echo ERROR: Update file not found at {new_exe_path} >> "%LOGFILE%"
    echo.
    echo Press any key to exit...
    pause > nul
    exit /b 1
)

echo Checking destination directory...
if exist "{current_exe_dir}" (
    echo [OK] Destination directory exists
    echo Destination dir exists >> "%LOGFILE%"
) else (
    echo [ERROR] Destination directory NOT FOUND: {current_exe_dir}
    echo ERROR: Destination directory not found >> "%LOGFILE%"
    echo.
    echo Press any key to exit...
    pause > nul
    exit /b 1
)

echo.
echo Executing copy command...
echo From: {new_exe_path}
echo   To: {current_exe_path}
echo.
copy /y /v "{new_exe_path}" "{current_exe_path}"
set COPY_ERROR=%ERRORLEVEL%
echo.
echo Copy command returned: %COPY_ERROR%
echo Copy command returned: %COPY_ERROR% >> "%LOGFILE%"

REM Check if copy succeeded by verifying destination exists
if not exist "{current_exe_path}" (
    echo.
    echo ERROR: Failed to copy new version!
    echo ERROR: Destination file not found after copy >> "%LOGFILE%"
    echo Copy error level was: %COPY_ERROR% >> "%LOGFILE%"
    echo.
    echo Attempting to restore backup...
    if exist "{current_exe_path}.old" (
        move /y "{current_exe_path}.old" "{current_exe_path}"
        echo Backup restored
        echo Backup restored >> "%LOGFILE%"
    )
    echo.
    echo Press any key to exit...
    pause > nul
    exit /b 1
)
echo.
echo Copy successful!
echo New version installed successfully.
echo New version installed successfully >> "%LOGFILE%"
dir "{current_exe_path}" >> "%LOGFILE%"
echo.

echo [4/5] Verifying installation...
echo [4/5] Verifying installation... >> "%LOGFILE%"
if not exist "{current_exe_path}" (
    echo ERROR: Installation verification failed!
    echo ERROR: Installation verification failed! >> "%LOGFILE%"
    pause
    exit /b 1
)
echo Installation verified.
echo Installation verified >> "%LOGFILE%"
echo.

echo [5/5] Starting Ghost Widget...
echo [5/5] Starting Ghost Widget... >> "%LOGFILE%"
cd /d "{current_exe_dir}"
echo Working directory: %CD%
echo Working directory: %CD% >> "%LOGFILE%"
echo Executable: {current_exe_path} >> "%LOGFILE%"

REM Wait longer for old PyInstaller temp files to be cleaned up
echo.
echo Waiting for old process cleanup (8 seconds)...
echo Waiting 8 seconds for PyInstaller temp cleanup... >> "%LOGFILE%"
timeout /t 8 /nobreak

REM Clean up any orphaned _MEI folders from old PyInstaller extractions
echo Cleaning up orphaned PyInstaller temp folders... >> "%LOGFILE%"
for /d %%G in ("%TEMP%\_MEI*") do (
    echo Removing old temp folder: %%G >> "%LOGFILE%"
    rd /s /q "%%G" 2>nul
)

echo Starting Ghost Widget...
start "" "{current_exe_path}"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start Ghost Widget!
    echo ERROR: Failed to start Ghost Widget (ErrorLevel=%ERRORLEVEL%) >> "%LOGFILE%"
    pause
    exit /b 1
)
echo Ghost Widget started successfully.
echo Ghost Widget started at %TIME% >> "%LOGFILE%"
echo.

echo.
echo Cleaning up...
echo Cleaning up... >> "%LOGFILE%"
echo Waiting 3 seconds...
timeout /t 3 /nobreak

echo.
echo Checking if new Ghost is running...
echo Checking if new Ghost is running... >> "%LOGFILE%"
tasklist /FI "IMAGENAME eq Ghost.exe" 2>NUL | find /I /N "Ghost.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo.
    echo ========================================
    echo   SUCCESS! Update Complete
    echo ========================================
    echo.
    echo Ghost Widget is now running with the latest version!
    echo.
    echo Ghost is running successfully! >> "%LOGFILE%"
    echo Cleaning up old files...
    if exist "{current_exe_path}.old" del /f /q "{current_exe_path}.old"
    if exist "{new_exe_path}" del /f /q "{new_exe_path}"
    echo Update completed successfully at %DATE% %TIME% >> "%LOGFILE%"
    echo.
    echo This window will close in 5 seconds...
    timeout /t 5 /nobreak > nul
) else (
    echo.
    echo ========================================
    echo   WARNING: Ghost did not start!
    echo ========================================
    echo.
    echo WARNING: Ghost did not start! >> "%LOGFILE%"
    echo Keeping backup file: {current_exe_path}.old
    echo Keeping downloaded file: {new_exe_path}
    echo Backup kept at: {current_exe_path}.old >> "%LOGFILE%"
    echo Downloaded file kept at: {new_exe_path} >> "%LOGFILE%"
    echo.
    echo Log file: %LOGFILE%
    echo.
    echo Press any key to attempt restore...
    pause > nul
    if exist "{current_exe_path}.old" (
        echo Restoring old version...
        echo Restoring old version... >> "%LOGFILE%"
        del /f /q "{current_exe_path}"
        move /y "{current_exe_path}.old" "{current_exe_path}" >> "%LOGFILE%" 2>&1
        echo Old version restored. Starting...
        echo Old version restored at %TIME% >> "%LOGFILE%"
        start "" "{current_exe_path}"
    )
    echo.
    echo Press any key to close...
    pause > nul
)

echo Update process finished. >> "%LOGFILE%"
(goto) 2>nul & del /f /q "%~f0"
"""

        with open(script_path, 'w') as f:
            f.write(script_content)

        # Log the batch script and log file locations
        self._log("info", f"Batch script path: {script_path}")
        self._log("info", f"Batch log file: {batch_log}")

        return str(script_path)

    def get_log_file_path(self) -> str:
        """Get the path to the update log file"""
        return str(self.log_file)

    def auto_update(self, progress_callback: Optional[Callable] = None) -> bool:
        """
        Convenience method to check, download, and install update in one go

        Args:
            progress_callback: Optional callback(stage, data) for progress updates
                stage can be: 'checking', 'downloading', 'installing'

        Returns:
            True if update was installed and app should restart
        """
        try:
            # Check for updates
            if progress_callback:
                progress_callback('checking', {'message': 'Checking for updates...'})

            update_info = self.check_for_updates()

            if not update_info or not update_info.get('available'):
                if progress_callback:
                    progress_callback('none', {'message': 'No updates available'})
                return False

            # Download update
            if progress_callback:
                progress_callback('downloading', {
                    'message': f"Downloading version {update_info['version']}...",
                    'version': update_info['version']
                })

            def download_progress(downloaded, total):
                if progress_callback:
                    percent = (downloaded / total * 100) if total > 0 else 0
                    print(f"📊 Download progress: {percent:.1f}% ({downloaded / 1024 / 1024:.1f}MB / {total / 1024 / 1024:.1f}MB)")
                    progress_callback('download_progress', {
                        'downloaded': downloaded,
                        'total': total,
                        'percent': percent
                    })

            installer_path = self.download_update(
                update_info['download_url'],
                filename=update_info.get('asset_name', 'Ghost.exe'),  # Use actual asset name
                progress_callback=download_progress
            )

            if not installer_path:
                if progress_callback:
                    progress_callback('error', {'message': 'Failed to download update'})
                return False

            # Download complete
            print(f"✓ Download complete: {installer_path}")
            if progress_callback:
                progress_callback('download_complete', {
                    'message': 'Download complete. Saving to current directory...',
                    'path': installer_path
                })

            # Save update to current directory
            if progress_callback:
                progress_callback('saving', {'message': 'Saving update file...'})

            success = self.install_update(installer_path)

            if success:
                print("✓ Update saved successfully to current directory")
                if progress_callback:
                    progress_callback('complete', {
                        'message': 'Update downloaded and saved! Close app to apply update.'
                    })
            else:
                print("❌ Failed to save update file")
                if progress_callback:
                    progress_callback('error', {'message': 'Failed to save update file'})

            return success

        except Exception as e:
            print(f"❌ Auto-update failed: {e}")
            if progress_callback:
                progress_callback('error', {'message': f'Update failed: {str(e)}'})
            return False


def check_for_updates_background(callback: Optional[Callable] = None):
    """
    Background function to check for updates without blocking

    Args:
        callback: Function to call with update info when check completes
    """
    import threading

    def check():
        checker = UpdateChecker()
        update_info = checker.check_for_updates()
        if callback and update_info:
            callback(update_info)

    thread = threading.Thread(target=check, daemon=True)
    thread.start()


def check_previous_update_status() -> Optional[Dict[str, Any]]:
    """
    Check if there was a previous update attempt and if it had issues

    Returns:
        Dictionary with status info if found, None otherwise
        {
            'success': bool,
            'log_file': str,
            'batch_log_file': str,
            'message': str
        }
    """
    import logging

    log_file = Path(tempfile.gettempdir()) / "ghost_widget_update.log"
    batch_log_file = Path(tempfile.gettempdir()) / "ghost_widget_update_batch.log"

    # Check if logs exist
    if not log_file.exists() and not batch_log_file.exists():
        return None

    result = {
        'success': True,
        'log_file': str(log_file) if log_file.exists() else None,
        'batch_log_file': str(batch_log_file) if batch_log_file.exists() else None,
        'message': ''
    }

    # Check batch log for errors
    if batch_log_file.exists():
        try:
            with open(batch_log_file, 'r', encoding='utf-8') as f:
                batch_content = f.read()

            if 'WARNING: Ghost did not start!' in batch_content:
                result['success'] = False
                result['message'] = 'Previous update failed - Ghost did not start after update'
            elif 'ERROR' in batch_content:
                result['success'] = False
                result['message'] = 'Previous update encountered errors'
            elif 'Update completed successfully' in batch_content:
                result['success'] = True
                result['message'] = 'Previous update completed successfully'
        except Exception as e:
            result['message'] = f'Could not read batch log: {e}'

    return result
