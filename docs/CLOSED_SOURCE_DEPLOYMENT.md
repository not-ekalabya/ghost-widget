# Closed Source App Deployment Guide

This guide explains how to use the auto-update system with a **closed-source** application where you don't want to share your source code publicly.

## Option 1: GitHub Private Repository (Recommended)

**Best for**: Teams, commercial products, apps with sensitive code

### Setup

1. **Make your repository private**:
   - Go to GitHub → Settings → Danger Zone
   - Click "Change visibility" → "Make private"

2. **Create a GitHub Personal Access Token** (for update checks):
   ```
   GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)

   Create new token with these permissions:
   ✓ repo (Full control of private repositories)
   ```

3. **Embed the token in your app**:

   ```python
   # version.py
   __version__ = "1.0.0"
   GITHUB_REPO = "your-username/ghost-widget-private"

   # For private repos, you need authentication
   # This token is embedded in the compiled app (users can't see it easily)
   GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   UPDATE_CHECK_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
   ```

4. **Update the updater initialization**:

   ```python
   # In main.py, modify the update check:
   def _check_for_updates_on_startup(self):
       def on_update_check_complete(update_info):
           if update_info and update_info.get('available'):
               _from_companion_q.put(("UPDATE_AVAILABLE", update_info))

       # Pass the GitHub token for private repos
       from version import GITHUB_TOKEN
       def check():
           checker = UpdateChecker(github_token=GITHUB_TOKEN)
           update_info = checker.check_for_updates()
           if callback and update_info:
               on_update_check_complete(update_info)

       thread = threading.Thread(target=check, daemon=True)
       thread.start()
   ```

### Releasing Updates

1. Build your executable (source code stays private)
2. Go to GitHub → Releases → New Release
3. Create release (only you can see it, but users can download assets with token)
4. Upload `Ghost.exe` as a release asset
5. Users automatically get notified!

**Security**:
- Source code stays private ✅
- Only release binaries are distributed ✅
- Token is embedded in compiled exe (hard to extract) ✅

---

## Option 2: GitHub Public Releases, Private Code

**Best for**: Free apps where you don't mind sharing binaries but want to keep code private

### Setup

This approach uses **release assets as public** even though the repo is private:

1. **Repository stays private** (code is hidden)
2. **Releases are created with public assets**
3. **Users can download .exe without authentication**

```python
# version.py - No token needed!
__version__ = "1.0.0"
GITHUB_REPO = "your-username/ghost-widget"
UPDATE_CHECK_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
```

### How to make release assets public:

When creating a release:
1. Upload `Ghost.exe` as usual
2. The executable download URL is publicly accessible even if repo is private
3. Update check works without authentication!

**Limitation**: Release metadata (changelog) requires authentication for private repos.

**Workaround**: Host a public `releases.json` file:

```python
# version.py
UPDATE_CHECK_URL = "https://your-website.com/ghost/releases.json"
```

```json
// releases.json (hosted on your website)
{
  "latest": {
    "version": "1.1.0",
    "download_url": "https://github.com/user/repo/releases/download/v1.1.0/Ghost.exe",
    "changelog": "What's new...",
    "published_at": "2024-01-15T10:00:00Z"
  }
}
```

---

## Option 3: Self-Hosted Updates (Complete Control)

**Best for**: Enterprise apps, apps with licensing, maximum control

### Setup

Host your own update server instead of using GitHub:

1. **Create an update server** (can be any web server):

```python
# Your web server returns this JSON
# https://yourdomain.com/api/ghost/latest
{
  "version": "1.1.0",
  "download_url": "https://yourdomain.com/downloads/Ghost-1.1.0.exe",
  "changelog": "What's new in 1.1.0...",
  "release_date": "2024-01-15",
  "checksum": "sha256_hash_of_exe",
  "mandatory": false  // Force users to update?
}
```

2. **Update version.py**:

```python
# version.py
__version__ = "1.0.0"
UPDATE_CHECK_URL = "https://yourdomain.com/api/ghost/latest"
```

3. **Modify updater.py** to handle your custom JSON format:

```python
# updater.py - modify check_for_updates()
def check_for_updates(self, timeout: int = 10):
    try:
        response = requests.get(self.update_url, timeout=timeout)
        data = response.json()

        latest_version = data['version']

        if self._is_newer_version(latest_version, self.current_version):
            return {
                'available': True,
                'version': latest_version,
                'current_version': self.current_version,
                'download_url': data['download_url'],
                'changelog': data['changelog'],
                'published_at': data['release_date'],
                'asset_name': 'Ghost.exe',
                'asset_size': 0,
                'release_url': 'https://yourdomain.com/releases'
            }

        return {'available': False}
    except Exception as e:
        print(f"Error checking for updates: {e}")
        return None
```

### Benefits of Self-Hosting:

✅ **Complete control** over update distribution
✅ **Add licensing checks** before allowing downloads
✅ **Usage analytics** (track who downloads updates)
✅ **Staged rollouts** (release to 10% of users first)
✅ **Pause/rollback** releases if issues found
✅ **Delta updates** (only download changed files)
✅ **Geographic CDN** for faster downloads worldwide

### Simple Self-Hosted Example (Flask):

```python
# update_server.py
from flask import Flask, jsonify, send_file

app = Flask(__name__)

LATEST_VERSION = {
    "version": "1.1.0",
    "download_url": "https://yourdomain.com/download/Ghost.exe",
    "changelog": "What's new...",
    "release_date": "2024-01-15"
}

@app.route('/api/ghost/latest')
def latest_version():
    return jsonify(LATEST_VERSION)

@app.route('/download/Ghost.exe')
def download_exe():
    # Optional: Add license check here
    return send_file('Ghost.exe', as_attachment=True)

if __name__ == '__main__':
    app.run()
```

Deploy this to:
- **AWS S3 + CloudFront** (cheapest)
- **DigitalOcean App Platform** (easiest)
- **Vercel/Netlify** (free tier available)
- **Your own VPS**

---

## Option 4: Hybrid Approach

**Best for**: Maximum flexibility

Use GitHub for version control + your own CDN for downloads:

```python
# version.py
__version__ = "1.0.0"
GITHUB_REPO = "your-username/ghost-widget-private"  # Private repo
CDN_URL = "https://cdn.yourdomain.com/ghost"  # Your CDN

# Check version from GitHub, download from CDN
UPDATE_CHECK_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DOWNLOAD_URL_OVERRIDE = f"{CDN_URL}/Ghost.exe"  # Override download URL
```

Benefits:
- GitHub handles version tracking
- Your CDN handles bandwidth
- Faster downloads for users
- Lower GitHub API rate limits

---

## Security Considerations for Closed Source

### 1. **Token Security**

If embedding a GitHub token in your app:

```python
# Don't commit plaintext tokens!
# Use encryption or obfuscation

from cryptography.fernet import Fernet

# Encrypted token (decrypt at runtime)
ENCRYPTED_TOKEN = b'gAAAAABh...'  # Encrypted version
KEY = b'your-encryption-key'  # Keep this safe!

def get_github_token():
    f = Fernet(KEY)
    return f.decrypt(ENCRYPTED_TOKEN).decode()
```

### 2. **Code Obfuscation**

Protect your compiled Python code:

```bash
# Use PyArmor for code obfuscation
pip install pyarmor

# Obfuscate your source before building
pyarmor pack main.py
```

### 3. **License Validation**

Add license checks to updates:

```python
# In updater.py
def check_for_updates(self, license_key: str):
    headers = {
        'X-License-Key': license_key
    }
    response = requests.get(self.update_url, headers=headers)

    if response.status_code == 403:
        return {'error': 'Invalid license'}

    # Continue with update check...
```

### 4. **Executable Signing**

Sign your .exe to build trust:

```bash
# Get code signing certificate
# Sign the executable
signtool sign /f cert.pfx /p password /t http://timestamp.digicert.com Ghost.exe
```

This prevents:
- Windows SmartScreen warnings
- Antivirus false positives
- Unauthorized modifications

---

## Comparison Table

| Feature | GitHub Private | Public Releases | Self-Hosted | Hybrid |
|---------|---------------|-----------------|-------------|---------|
| **Source Code Privacy** | ✅ Private | ✅ Private | ✅ Private | ✅ Private |
| **Setup Complexity** | Easy | Easy | Medium | Medium |
| **Cost** | Free* | Free | $$ | $ |
| **Bandwidth Limits** | GitHub's | GitHub's | Unlimited | Your choice |
| **Custom Logic** | Limited | Limited | Full control | Partial |
| **License Checks** | ❌ No | ❌ No | ✅ Yes | ✅ Yes |
| **Analytics** | Limited | Limited | Full | Full |
| **Rollback Speed** | Fast | Fast | Instant | Instant |

*GitHub private repos are free for individual accounts

---

## Recommended Setup for Closed Source

For most closed-source apps, I recommend:

### Small/Solo Projects:
→ **Option 1: GitHub Private Repository**
- Easiest to set up
- No infrastructure to maintain
- Free for individuals
- Works perfectly with current implementation

### Commercial/Enterprise:
→ **Option 3: Self-Hosted Updates**
- Full control over distribution
- License validation
- Usage analytics
- Professional appearance

### Hybrid (Best of both):
→ **Option 4: GitHub + CDN**
- Use GitHub for version management
- Use CDN (CloudFlare/AWS) for binary distribution
- Get analytics + cost optimization

---

## Migration Path

Start simple, scale as needed:

1. **Phase 1**: Use GitHub private repo (quick start)
2. **Phase 2**: Add your own CDN for downloads (scale)
3. **Phase 3**: Move to self-hosted with licensing (enterprise)

The auto-update code is flexible enough to support all these approaches with minimal changes!

---

## Quick Start for Closed Source

**Fastest way to get started TODAY**:

1. Make your GitHub repo private
2. Create a personal access token
3. Add token to `version.py`
4. Build and create a private release
5. Done! Only you and your users (with the app) can access it

Your source code stays 100% private while users get seamless auto-updates! 🎉
