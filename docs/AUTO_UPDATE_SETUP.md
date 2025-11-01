# Auto-Update System Setup Guide

Ghost Widget includes an automatic update system that checks for new releases on GitHub and allows users to download and install updates with one click.

## How It Works

1. **On Startup**: App checks GitHub for the latest release
2. **Update Available**: Shows a beautiful notification dialog with changelog
3. **One-Click Install**: User clicks "Download & Install" to automatically update
4. **Seamless Restart**: App restarts with the new version

## Setup Instructions

### 1. Update Version Configuration

Edit `version.py` and update the following:

```python
__version__ = "1.0.0"  # Current version
GITHUB_REPO = "your-username/ghost-widget"  # Your GitHub repo
```

### 2. Configure GitHub Repository

In `version.py`, set your actual GitHub repository:

```python
GITHUB_REPO = "yourusername/ghost-widget"
```

### 3. Create GitHub Releases

When you want to push an update:

#### Step 1: Update Version Number

Update the version in `version.py`:
```python
__version__ = "1.1.0"  # Increment version
```

#### Step 2: Build the Executable

```bash
# Build with PyInstaller
pyinstaller main.spec

# The executable will be in dist/Ghost.exe
```

#### Step 3: Create GitHub Release

1. Go to your GitHub repository
2. Click "Releases" → "Draft a new release"
3. Fill in the details:
   - **Tag version**: `v1.1.0` (must start with 'v')
   - **Release title**: `Ghost v1.1.0`
   - **Description**: Write your changelog
     ```markdown
     ## What's New in v1.1.0

     ### Features
     - ✨ Added automatic updates
     - 🎨 Improved UI design
     - 🚀 Performance improvements

     ### Bug Fixes
     - 🐛 Fixed memory access in built app
     - 🐛 Fixed context retrieval issue
     ```
4. **Upload the executable**: Drag and drop `dist/Ghost.exe` to the release assets
5. Click "Publish release"

### 4. Testing Updates

To test the update system:

1. Build version 1.0.0 and create a release
2. Install and run the app
3. Update version to 1.1.0 in `version.py`
4. Build the new executable
5. Create a new release (v1.1.0) with the new executable
6. Run the old app (1.0.0) - it should detect and offer the update

## Update Process for Users

### Automatic Check
- App checks for updates on startup (background, non-blocking)
- No interruption to user workflow

### Update Dialog
When an update is available, users see:
- Current version vs new version
- Full changelog
- Three options:
  - **Download & Install**: Downloads and installs automatically
  - **View on GitHub**: Opens release page in browser
  - **Later**: Dismisses the dialog

### Installation Process
1. User clicks "Download & Install"
2. Progress bar shows download progress
3. When complete, app automatically:
   - Backs up current version
   - Replaces with new version
   - Restarts the app

## Advanced: Customizing Update Behavior

### Change Update Check Frequency

By default, updates are checked only on startup. To add periodic checks:

```python
# In OverlayWindow.__init__
def check_updates_periodically(self):
    """Check for updates every 24 hours"""
    if UPDATER_AVAILABLE:
        check_for_updates_background(callback=lambda info:
            _from_companion_q.put(("UPDATE_AVAILABLE", info)) if info and info.get('available') else None
        )

    # Schedule next check in 24 hours
    QTimer.singleShot(24 * 60 * 60 * 1000, self.check_updates_periodically)

# Call it after startup
self.check_updates_periodically()
```

### Silent Auto-Updates (Like Cursor)

To make updates completely automatic:

```python
def _check_for_updates_on_startup(self):
    """Auto-download and install updates silently"""
    def on_update_check_complete(update_info):
        if update_info and update_info.get('available'):
            # Auto-download without user prompt
            checker = UpdateChecker()
            def progress(stage, data):
                if stage == 'complete':
                    # Show toast notification
                    self.signals.log.emit(
                        f"<span style='color: #10B981;'>✓ Updated to v{update_info['version']}! "
                        f"Restart to apply.</span>"
                    )

            checker.auto_update(progress_callback=progress)

    check_for_updates_background(callback=on_update_check_complete)
```

### Update Channels (Stable/Beta)

To support multiple update channels:

```python
# version.py
UPDATE_CHANNEL = "stable"  # or "beta", "nightly"

# When creating releases, tag them as:
# v1.1.0 (stable)
# v1.1.0-beta (beta channel)

# In updater.py, filter by channel
def check_for_updates(self, channel="stable"):
    # Filter releases by channel tag
    pass
```

## Troubleshooting

### Update Not Detected

**Issue**: App doesn't show update notification

**Solutions**:
1. Check GitHub repo is set correctly in `version.py`
2. Ensure release is published (not draft)
3. Verify release tag starts with 'v' (e.g., `v1.1.0`)
4. Check internet connection
5. Look at console output for errors

### Download Fails

**Issue**: Update download fails or times out

**Solutions**:
1. Check internet connection
2. Try downloading manually from GitHub
3. Check firewall/antivirus settings
4. Release asset must be named with `.exe` extension

### Installation Fails

**Issue**: Update downloads but doesn't install

**Solutions**:
1. Check if app has write permissions to its directory
2. Try running as administrator
3. Disable antivirus temporarily
4. Check if app is running from a restricted location (e.g., Program Files)

### Version Comparison Issues

**Issue**: App doesn't recognize newer version

**Solutions**:
1. Ensure version numbers follow semantic versioning (X.Y.Z)
2. Don't use extra characters in version strings
3. Tag format must be `v1.2.3` (not `version-1.2.3` or `release-1.2.3`)

## Best Practices

### 1. Semantic Versioning
Use semantic versioning (MAJOR.MINOR.PATCH):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

### 2. Detailed Changelogs
Write clear changelogs in releases:
```markdown
## What's New

### ✨ Features
- Added automatic updates
- Improved memory management

### 🐛 Bug Fixes
- Fixed crash on startup
- Fixed memory leak

### 🔧 Improvements
- Faster startup time
- Better error messages
```

### 3. Test Before Release
1. Build the executable
2. Test on a clean machine
3. Verify all features work
4. Check for missing dependencies
5. Then create the release

### 4. Staged Rollouts
For large user bases:
1. Release to beta channel first
2. Monitor for issues
3. After 24-48 hours, promote to stable

### 5. Keep Old Versions
Don't delete old releases - users may need to downgrade if issues occur

## Security Considerations

### Code Signing
For production, sign your executables:

```bash
# Get a code signing certificate from a trusted CA
# Sign the executable before releasing
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com Ghost.exe
```

This prevents Windows SmartScreen warnings.

### Checksum Verification
The updater includes SHA256 checksum verification to ensure download integrity.

### HTTPS Only
All downloads use HTTPS from GitHub's CDN - no man-in-the-middle attacks possible.

## Monitoring Updates

### Track Update Adoption

Add analytics to track update success:

```python
# In updater.py, after successful update
def track_update(old_version, new_version):
    # Send to your analytics service
    pass
```

### Error Reporting

Log update failures for debugging:

```python
def on_update_error(error):
    # Send error report to your server
    print(f"Update failed: {error}")
```

## FAQ

**Q: How often does it check for updates?**
A: Once on startup. Can be configured for periodic checks.

**Q: Does it work offline?**
A: Update check fails gracefully if offline - no errors shown to user.

**Q: Can users disable auto-update?**
A: You can add a settings toggle if desired.

**Q: What if a release is broken?**
A: Users can download previous versions from GitHub releases page.

**Q: How big can updates be?**
A: No size limit, but consider user bandwidth. Show download size in dialog.

## Next Steps

1. ✅ Set your GitHub repository in `version.py`
2. ✅ Build and test the app locally
3. ✅ Create your first GitHub release
4. ✅ Test the update mechanism
5. ✅ (Optional) Set up code signing
6. ✅ Deploy to users!

Now whenever you push a new feature to the main branch, just create a new GitHub release and all users will automatically get notified and can update with one click!
