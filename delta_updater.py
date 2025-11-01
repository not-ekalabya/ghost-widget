"""
Delta Update System for Ghost Widget
Uses binary diffing to download only changes between versions
"""

import os
import hashlib
import requests
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Callable
import json

try:
    import bsdiff4
    BSDIFF_AVAILABLE = True
except ImportError:
    BSDIFF_AVAILABLE = False
    print("⚠️ bsdiff4 not available. Install with: pip install bsdiff4")


class DeltaUpdater:
    """Handles delta updates using binary diffing"""

    def __init__(self, current_exe_path: str, update_server_url: str):
        """
        Initialize delta updater

        Args:
            current_exe_path: Path to current executable
            update_server_url: Base URL for update server
        """
        self.current_exe_path = current_exe_path
        self.update_server_url = update_server_url

    def get_current_hash(self) -> str:
        """Get SHA256 hash of current executable"""
        sha256 = hashlib.sha256()
        with open(self.current_exe_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    def check_for_delta_update(self, target_version: str) -> Optional[Dict[str, Any]]:
        """
        Check if a delta update is available

        Args:
            target_version: Target version to update to

        Returns:
            Dict with delta update info, or None if not available
        """
        try:
            current_hash = self.get_current_hash()

            # Request delta patch from server
            response = requests.get(
                f"{self.update_server_url}/delta/{current_hash}/{target_version}",
                timeout=10
            )

            if response.status_code == 404:
                # No delta available, need full download
                return None

            if response.status_code != 200:
                print(f"⚠️ Delta check failed: {response.status_code}")
                return None

            delta_info = response.json()

            return {
                'available': True,
                'patch_url': delta_info['patch_url'],
                'patch_size': delta_info['patch_size'],
                'target_hash': delta_info['target_hash'],
                'target_version': target_version,
                'savings_percent': delta_info.get('savings_percent', 0)
            }

        except Exception as e:
            print(f"⚠️ Error checking for delta update: {e}")
            return None

    def download_and_apply_delta(
        self,
        delta_info: Dict[str, Any],
        progress_callback: Optional[Callable] = None
    ) -> Optional[str]:
        """
        Download delta patch and apply it

        Args:
            delta_info: Delta update information
            progress_callback: Optional callback(stage, data) for progress

        Returns:
            Path to new executable, or None if failed
        """
        if not BSDIFF_AVAILABLE:
            print("❌ bsdiff4 not available, cannot apply delta")
            return None

        try:
            # Download patch
            if progress_callback:
                progress_callback('downloading', {'message': 'Downloading delta patch...'})

            patch_path = self._download_patch(
                delta_info['patch_url'],
                delta_info['patch_size'],
                progress_callback
            )

            if not patch_path:
                return None

            # Apply patch
            if progress_callback:
                progress_callback('applying', {'message': 'Applying delta patch...'})

            new_exe_path = self._apply_patch(patch_path)

            if not new_exe_path:
                return None

            # Verify hash
            if progress_callback:
                progress_callback('verifying', {'message': 'Verifying update...'})

            if not self._verify_hash(new_exe_path, delta_info['target_hash']):
                print("❌ Hash verification failed!")
                os.remove(new_exe_path)
                return None

            if progress_callback:
                progress_callback('complete', {
                    'message': 'Delta update applied successfully!',
                    'savings': f"Saved {delta_info.get('savings_percent', 0)}% bandwidth"
                })

            return new_exe_path

        except Exception as e:
            print(f"❌ Error applying delta update: {e}")
            return None

    def _download_patch(
        self,
        patch_url: str,
        patch_size: int,
        progress_callback: Optional[Callable] = None
    ) -> Optional[str]:
        """Download the delta patch file"""
        try:
            temp_dir = Path(tempfile.gettempdir()) / "ghost_delta"
            temp_dir.mkdir(exist_ok=True)

            patch_path = temp_dir / "update.patch"

            response = requests.get(patch_url, stream=True, timeout=300)
            response.raise_for_status()

            downloaded = 0
            with open(patch_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback:
                            percent = (downloaded / patch_size * 100) if patch_size > 0 else 0
                            progress_callback('download_progress', {
                                'downloaded': downloaded,
                                'total': patch_size,
                                'percent': percent
                            })

            return str(patch_path)

        except Exception as e:
            print(f"❌ Error downloading patch: {e}")
            return None

    def _apply_patch(self, patch_path: str) -> Optional[str]:
        """Apply binary patch to create new executable"""
        try:
            temp_dir = Path(tempfile.gettempdir()) / "ghost_delta"
            new_exe_path = temp_dir / "Ghost_new.exe"

            # Read current exe
            with open(self.current_exe_path, 'rb') as f:
                old_data = f.read()

            # Read patch
            with open(patch_path, 'rb') as f:
                patch_data = f.read()

            # Apply patch using bsdiff4
            new_data = bsdiff4.patch(old_data, patch_data)

            # Write new exe
            with open(new_exe_path, 'wb') as f:
                f.write(new_data)

            return str(new_exe_path)

        except Exception as e:
            print(f"❌ Error applying patch: {e}")
            return None

    def _verify_hash(self, file_path: str, expected_hash: str) -> bool:
        """Verify file hash matches expected"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)

        actual_hash = sha256.hexdigest()
        return actual_hash == expected_hash


class HybridUpdater:
    """
    Hybrid updater that tries delta updates first, falls back to full download
    Combines DeltaUpdater and UpdateChecker for best user experience
    """

    def __init__(self, current_exe_path: str, update_server_url: str, full_updater):
        """
        Initialize hybrid updater

        Args:
            current_exe_path: Path to current executable
            update_server_url: Base URL for update server (for delta updates)
            full_updater: UpdateChecker instance for full downloads
        """
        self.delta_updater = DeltaUpdater(current_exe_path, update_server_url) if BSDIFF_AVAILABLE else None
        self.full_updater = full_updater

    def smart_update(
        self,
        target_version: str,
        download_url: str,
        progress_callback: Optional[Callable] = None
    ) -> Optional[str]:
        """
        Smart update: Try delta first, fall back to full download

        Args:
            target_version: Version to update to
            download_url: URL for full download (fallback)
            progress_callback: Progress callback

        Returns:
            Path to new executable
        """
        # Try delta update first
        if self.delta_updater and BSDIFF_AVAILABLE:
            if progress_callback:
                progress_callback('checking_delta', {
                    'message': 'Checking for delta update...'
                })

            delta_info = self.delta_updater.check_for_delta_update(target_version)

            if delta_info:
                print(f"✨ Delta update available! Saving {delta_info.get('savings_percent', 0)}% bandwidth")

                new_exe = self.delta_updater.download_and_apply_delta(
                    delta_info,
                    progress_callback
                )

                if new_exe:
                    return new_exe

                print("⚠️ Delta update failed, falling back to full download")

        # Fall back to full download
        if progress_callback:
            progress_callback('full_download', {
                'message': 'Downloading full update...'
            })

        return self.full_updater.download_update(download_url, progress_callback)


# Server-side: Generate delta patches
class DeltaPatchGenerator:
    """
    Server-side tool to generate delta patches between versions
    Run this when creating a new release
    """

    @staticmethod
    def generate_patch(old_exe_path: str, new_exe_path: str, output_patch_path: str) -> Dict[str, Any]:
        """
        Generate a binary diff patch

        Args:
            old_exe_path: Path to old version exe
            new_exe_path: Path to new version exe
            output_patch_path: Where to save the patch file

        Returns:
            Dict with patch information
        """
        if not BSDIFF_AVAILABLE:
            raise ImportError("bsdiff4 required. Install with: pip install bsdiff4")

        # Read files
        with open(old_exe_path, 'rb') as f:
            old_data = f.read()

        with open(new_exe_path, 'rb') as f:
            new_data = f.read()

        # Generate patch
        patch_data = bsdiff4.diff(old_data, new_data)

        # Save patch
        with open(output_patch_path, 'wb') as f:
            f.write(patch_data)

        # Calculate hashes
        old_hash = hashlib.sha256(old_data).hexdigest()
        new_hash = hashlib.sha256(new_data).hexdigest()

        # Calculate savings
        old_size = len(old_data)
        new_size = len(new_data)
        patch_size = len(patch_data)
        savings_percent = (1 - patch_size / new_size) * 100

        print(f"✓ Delta patch generated:")
        print(f"  Old version: {old_size:,} bytes")
        print(f"  New version: {new_size:,} bytes")
        print(f"  Patch size: {patch_size:,} bytes")
        print(f"  Bandwidth savings: {savings_percent:.1f}%")

        return {
            'old_hash': old_hash,
            'new_hash': new_hash,
            'old_size': old_size,
            'new_size': new_size,
            'patch_size': patch_size,
            'savings_percent': savings_percent,
            'patch_path': output_patch_path
        }

    @staticmethod
    def generate_patch_manifest(versions_dir: str, output_manifest: str):
        """
        Generate a manifest of all available delta patches

        Args:
            versions_dir: Directory containing version subdirectories
            output_manifest: Path to save manifest JSON

        Structure:
            versions/
              1.0.0/
                Ghost.exe
              1.1.0/
                Ghost.exe
                patches/
                  from_1.0.0.patch
        """
        manifest = {}

        versions_path = Path(versions_dir)
        for version_dir in sorted(versions_path.iterdir()):
            if not version_dir.is_dir():
                continue

            version = version_dir.name
            exe_path = version_dir / "Ghost.exe"

            if not exe_path.exists():
                continue

            # Get exe hash
            with open(exe_path, 'rb') as f:
                exe_hash = hashlib.sha256(f.read()).hexdigest()

            patches_dir = version_dir / "patches"
            patches = []

            if patches_dir.exists():
                for patch_file in patches_dir.glob("from_*.patch"):
                    # Extract source version from filename
                    source_version = patch_file.stem.replace("from_", "")

                    patch_size = patch_file.stat().st_size

                    patches.append({
                        'from_version': source_version,
                        'patch_file': str(patch_file.relative_to(versions_path)),
                        'patch_size': patch_size
                    })

            manifest[version] = {
                'exe_hash': exe_hash,
                'exe_size': exe_path.stat().st_size,
                'patches': patches
            }

        # Save manifest
        with open(output_manifest, 'w') as f:
            json.dump(manifest, f, indent=2)

        print(f"✓ Manifest generated: {output_manifest}")
        return manifest


# Example usage for generating patches when creating a release
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage:")
        print("  Generate patch: python delta_updater.py generate old.exe new.exe output.patch")
        print("  Generate manifest: python delta_updater.py manifest versions_dir manifest.json")
        sys.exit(1)

    command = sys.argv[1]

    if command == "generate":
        old_exe = sys.argv[2]
        new_exe = sys.argv[3]
        output = sys.argv[4]

        info = DeltaPatchGenerator.generate_patch(old_exe, new_exe, output)
        print(f"\n✓ Patch saved to: {output}")

    elif command == "manifest":
        versions_dir = sys.argv[2]
        output = sys.argv[3]

        DeltaPatchGenerator.generate_patch_manifest(versions_dir, output)
