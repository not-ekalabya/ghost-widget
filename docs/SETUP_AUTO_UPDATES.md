# Auto-Update Setup Guide for Ghost Widget

## Current Status
❌ Auto-updates are **NOT working** because:
1. GitHub repository `not-ekalabya/ghost-widget` doesn't exist yet
2. No releases have been created

## Quick Fix (5 minutes)

### Step 1: Create GitHub Repository

**Option A: Via GitHub Website** (Easiest)
1. Go to https://github.com/new
2. Owner: `not-ekalabya`
3. Repository name: `ghost-widget`
4. Description: "AI-powered context capture and retrieval assistant"
5. Choose **Private** (recommended) or Public
6. **DO NOT** check "Add a README file"
7. Click **"Create repository"**

**Option B: Via Git Push** (If repo was created but not pushed)
```bash
cd C:\projects\ghost-widget
git push -u origin main
```

### Step 2: Build Your Executable

```bash
cd C:\projects\ghost-widget
pyinstaller main.spec
```

Your executable will be at: `dist\Ghost.exe`

### Step 3: Create Your First Release

1. Go to your GitHub repo: https://github.com/not-ekalabya/ghost-widget
2. Click on "Releases" (right sidebar)
3. Click "Create a new release" or "Draft a new release"
4. Fill in the details:

   **Tag version:** `v1.0.0` (MUST start with 'v')

   **Release title:** `Ghost v1.0.0 - Initial Release`

   **Description:**
   ```markdown
   ## 🎉 Initial Release

   ### Features
   - ✨ Screen capture and context tracking
   - 💬 AI-powered chat with Gemini and Claude
   - 🧠 Memory management with mem0
   - 🔗 GitHub integration
   - 🔄 Automatic updates
   - 📊 Chat history
   - ⚙️ Customizable settings

   ### Installation
   1. Download `Ghost.exe`
   2. Run the executable
   3. Follow onboarding

   ### System Requirements
   - Windows 10/11
   - Internet connection
   ```

5. **Upload the executable:**
   - Click "Attach binaries by dropping them here or selecting them"
   - Select `dist\Ghost.exe`
   - Wait for upload to complete

6. Click **"Publish release"**

### Step 4: Test Auto-Updates

1. **Keep v1.0.0 installed** on your machine
2. **Update version.py** to v1.0.1:
   ```python
   __version__ = "1.0.1"
   ```
3. **Build new version:**
   ```bash
   pyinstaller main.spec
   ```
4. **Create v1.0.1 release** on GitHub:
   - Tag: `v1.0.1`
   - Title: `Ghost v1.0.1 - Auto-Update Test`
   - Upload new `dist\Ghost.exe`
5. **Run the OLD v1.0.0 app**
6. It should detect and offer to install v1.0.1!

### Step 5: Verify in Version Tab

1. Launch the app
2. Go to "Version" tab
3. Click "Check for Updates Now"
4. Watch the logs to see what's happening

## Troubleshooting

### Error: "HTTP 404 - Not Found"

**Cause:** Repository or release doesn't exist

**Fix:**
- Verify repo exists: https://github.com/not-ekalabya/ghost-widget
- Verify at least one release exists
- Check that release tag starts with 'v' (e.g., `v1.0.0`)

### Error: "HTTP 403 - Forbidden"

**Cause:** GitHub token is invalid or expired

**Fix:**
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token with `repo` scope
3. Update `updater.py` line 39:
   ```python
   self.github_token = "YOUR_NEW_TOKEN_HERE"
   ```

### Error: "No Windows executable found in release assets"

**Cause:** You didn't upload the .exe file

**Fix:**
- Go to the release on GitHub
- Edit the release
- Upload `Ghost.exe` file
- Save changes

### Error: "Network timeout"

**Cause:** Firewall or no internet connection

**Fix:**
- Check internet connection
- Check firewall settings
- Try accessing https://api.github.com/repos/not-ekalabya/ghost-widget/releases/latest in browser

## For Private Repositories

Your updater is already configured for private repos. Set your GitHub token in the environment variable `GITHUB_TOKEN`.

**Permissions needed:**
- ✅ `repo` - Full control of private repositories

## Version Tab Features

The new Version tab shows:
- ✅ Current version
- ✅ Auto-update system status
- ✅ GitHub repository
- ✅ Update check URL
- ✅ Real-time update logs
- ✅ Manual "Check for Updates Now" button
- ✅ Detailed error messages with timestamps

## Release Checklist

Every time you want to release an update:

- [ ] Update `__version__` in `version.py`
- [ ] Build: `pyinstaller main.spec`
- [ ] Test the executable locally
- [ ] Create GitHub release with tag (e.g., `v1.1.0`)
- [ ] Upload `dist\Ghost.exe` to the release
- [ ] Write meaningful changelog
- [ ] Publish release
- [ ] Test update on old version

## Current Configuration

**Repository:** `not-ekalabya/ghost-widget`
**Current Version:** `1.0.0`
**Update Check URL:** `https://api.github.com/repos/not-ekalabya/ghost-widget/releases/latest`
**Authentication:** GitHub token (for private repo)
**Auto-check on startup:** Enabled (currently fails due to no releases)

## Next Steps

1. ✅ Create GitHub repository `not-ekalabya/ghost-widget`
2. ✅ Push your code to GitHub
3. ✅ Build Ghost.exe with `pyinstaller main.spec`
4. ✅ Create v1.0.0 release on GitHub
5. ✅ Upload Ghost.exe to the release
6. ✅ Test by checking Version tab
7. ✅ Create v1.0.1 test release
8. ✅ Verify auto-update works!

---

**Need help?** Check the logs in the Version tab for detailed debugging information.
