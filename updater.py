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
        self.github_token = "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"
        self.download_progress_callback: Optional[Callable] = None

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
                    download_url = asset['browser_download_url']
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

    def download_update(self, download_url: str, progress_callback: Optional[Callable] = None) -> Optional[str]:
        """
        Download update from URL

        Args:
            download_url: URL to download the update from
            progress_callback: Optional callback(downloaded_bytes, total_bytes) for progress updates

        Returns:
            Path to downloaded file, or None if failed
        """
        try:
            print(f"📥 Downloading update from: {download_url}")

            # Create temp directory for download
            temp_dir = Path(tempfile.gettempdir()) / "ghost_updates"
            temp_dir.mkdir(exist_ok=True)

            # Extract filename from URL
            filename = download_url.split('/')[-1]
            download_path = temp_dir / filename

            # Download with progress tracking
            response = requests.get(download_url, stream=True, timeout=300)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            with open(download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        if progress_callback:
                            progress_callback(downloaded_size, total_size)

            print(f"✓ Update downloaded to: {download_path}")
            return str(download_path)

        except Exception as e:
            print(f"❌ Error downloading update: {e}")
            return None

    def install_update(self, installer_path: str, silent: bool = True) -> bool:
        """
        Install the downloaded update

        Args:
            installer_path: Path to the downloaded installer
            silent: If True, install silently without user interaction

        Returns:
            True if installation started successfully
        """
        try:
            if not os.path.exists(installer_path):
                print(f"❌ Installer not found: {installer_path}")
                return False

            print(f"🚀 Installing update from: {installer_path}")

            # Determine if we're running as a frozen executable
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                current_exe = sys.executable

                # Create a batch script to replace the executable after app closes
                batch_script = self._create_update_script(installer_path, current_exe)

                # Launch the batch script and exit
                subprocess.Popen(
                    ['cmd', '/c', batch_script],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

                print("✓ Update process started. Application will restart...")
                return True
            else:
                # Running in development mode - just open the installer
                if sys.platform == 'win32':
                    os.startfile(installer_path)
                else:
                    subprocess.Popen([installer_path])
                return True

        except Exception as e:
            print(f"❌ Error installing update: {e}")
            return False

    def _create_update_script(self, new_exe_path: str, current_exe_path: str) -> str:
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

        # Batch script that:
        # 1. Waits for current process to exit
        # 2. Backs up old executable
        # 3. Copies new executable
        # 4. Restarts application
        # 5. Cleans up

        script_content = f"""@echo off
echo Waiting for Ghost to close...
timeout /t 2 /nobreak > nul

echo Backing up current version...
move /y "{current_exe_path}" "{current_exe_path}.old"

echo Installing new version...
copy /y "{new_exe_path}" "{current_exe_path}"

echo Starting Ghost...
start "" "{current_exe_path}"

echo Cleaning up...
timeout /t 2 /nobreak > nul
del "{current_exe_path}.old"
del "{new_exe_path}"
del "%~f0"
"""

        with open(script_path, 'w') as f:
            f.write(script_content)

        return str(script_path)

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
                    progress_callback('download_progress', {
                        'downloaded': downloaded,
                        'total': total,
                        'percent': (downloaded / total * 100) if total > 0 else 0
                    })

            installer_path = self.download_update(
                update_info['download_url'],
                progress_callback=download_progress
            )

            if not installer_path:
                if progress_callback:
                    progress_callback('error', {'message': 'Failed to download update'})
                return False

            # Install update
            if progress_callback:
                progress_callback('installing', {'message': 'Installing update...'})

            success = self.install_update(installer_path)

            if success and progress_callback:
                progress_callback('complete', {
                    'message': 'Update installed successfully. Restarting...'
                })

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
