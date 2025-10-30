# Recording and Screenshot Saving Guide

## Overview

By default, Ghost Widget **does not save** video recordings or screenshots to disk to save storage space and respect privacy. However, the recording functionality is still active and captures frames in memory for AI analysis.

If you need to save recordings and screenshots for debugging, review, or documentation purposes, you can enable this feature.

## Enabling Recordings and Screenshots

### Method 1: Enable in Backend Initialization (Recommended)

Edit `backend.py` or wherever you initialize the `BackgroundCompanion`:

```python
companion = BackgroundCompanion(
    api_key="your_api_key",
    # ... other parameters ...
    save_recordings=True  # Enable saving to disk
)
```

### Method 2: Enable from Main Application

If you're initializing the companion from `main.py`:

```python
# Find the companion initialization in main.py
companion = BackgroundCompanion(
    api_key=GEMINI_API_KEY,
    db_path=db_path,
    watch_dirs=config.get("watch_dirs", []),
    user_id=config.get("user_id", "default_user"),
    progress_callback=progress_callback,
    qa_model=config.get("qa_model", "gemini"),
    recording_fps=config.get("fps", 1),
    analysis_interval=config.get("analysis_interval", 40),
    save_recordings=True  # Add this parameter
)
```

## What Gets Saved

When `save_recordings=True`, the following files are saved:

### 1. Video Recordings

**Location:** `./recordings/` directory

**Files:**
- `full_recording_YYYYMMDD_HHMMSS.mp4` - Complete recording with all frames
- `condensed_recording_YYYYMMDD_HHMMSS.mp4` - Optimized recording with only changed frames (sent to AI)

**Details:**
- Videos are recorded at the configured FPS (default: 1 frame per second)
- Full recordings contain every frame captured
- Condensed recordings skip duplicate/static frames for efficient AI analysis
- Files are automatically timestamped

### 2. Screenshots (Guidance Mode)

**Location:** `./screenshots/` directory

**Files:**
- `guidance_YYYYMMDD_HHMMSS.png` - Screenshots captured during Guidance Mode queries

**Details:**
- Only captured when using Guidance Mode (the checkbox in the UI)
- Temporary screenshots are automatically cleaned up after use
- Only saved to disk when `save_recordings=True`

## Storage Considerations

### Disk Space Usage

With `save_recordings=True`:
- **Full recordings:** ~1-5 MB per minute (depending on screen resolution and FPS)
- **Condensed recordings:** ~30-70% smaller than full recordings
- **Screenshots:** ~500 KB - 2 MB per screenshot

### Example Usage Over Time

**1 hour of recording at 1 FPS:**
- Full recording: ~60-120 MB
- Condensed recording: ~20-50 MB

**8 hours of daily use:**
- Full recordings: ~500 MB - 1 GB per day
- Condensed recordings: ~200-400 MB per day

## Cleaning Up Old Recordings

Recordings are not automatically deleted. To manage disk space:

### Manual Cleanup

```bash
# Delete recordings older than 7 days (Windows PowerShell)
Get-ChildItem -Path "recordings" -Recurse | Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-7)} | Remove-Item

# Delete recordings older than 7 days (Linux/Mac)
find recordings -type f -mtime +7 -delete
```

### Automated Cleanup Script

Create a script to run periodically:

```python
# cleanup_recordings.py
from pathlib import Path
from datetime import datetime, timedelta

def cleanup_old_recordings(days=7):
    recordings_dir = Path("recordings")
    cutoff_date = datetime.now() - timedelta(days=days)

    for file in recordings_dir.glob("*.mp4"):
        if datetime.fromtimestamp(file.stat().st_mtime) < cutoff_date:
            file.unlink()
            print(f"Deleted: {file.name}")

if __name__ == "__main__":
    cleanup_old_recordings(days=7)
```

## Use Cases

### When to Enable Recording Saving

✅ **Enable when:**
- Debugging issues with screen capture
- Creating documentation or demos
- Reviewing your work activity
- Training or showing examples
- Compliance or audit requirements

❌ **Keep disabled when:**
- Limited disk space
- Privacy concerns
- Don't need playback/review
- Just using for AI analysis (memory-only is sufficient)

## Privacy and Security

### Privacy Considerations

- Recordings capture your entire screen
- May include sensitive information (passwords, documents, conversations)
- Consider what's visible before enabling recording saving
- Review and delete recordings regularly

### Security Best Practices

1. **Encrypt the recordings folder** if storing sensitive data
2. **Use `.gitignore`** to prevent recordings from being committed to git
3. **Set appropriate file permissions** on the recordings directory
4. **Regular cleanup** of old recordings you no longer need

### Git Ignore (Already Configured)

The project `.gitignore` should already exclude:
```gitignore
recordings/
screenshots/
*.mp4
*.png
```

## Technical Details

### Recording Pipeline

1. **Capture:** Screen frames captured at configured FPS
2. **Storage:** Frames stored in memory during recording session
3. **Processing:** AI analyzes frames for activity detection
4. **Saving:** If `save_recordings=True`, creates two videos:
   - Full video (all frames)
   - Condensed video (only changed frames for AI)
5. **Cleanup:** Memory cleared after analysis

### Frame Deduplication

The condensed video uses intelligent frame deduplication:
- Compares frames using perceptual hashing
- Skips static/duplicate frames
- Keeps only frames with visual changes
- Typically reduces size by 30-70%

### Video Codecs

- **Windows:** Uses `mp4v` codec
- **Linux/Mac:** Uses `avc1` (H.264) codec
- Output format: MP4 container

## Troubleshooting

### Recordings Not Being Saved

**Check:**
1. `save_recordings` parameter is set to `True`
2. `recordings/` directory exists and is writable
3. Sufficient disk space available
4. No permission issues with the directory

### Video Files Corrupted

**Solutions:**
- Check codec compatibility on your system
- Try different video codec (edit `backend.py`)
- Ensure recording completed before stopping app
- Verify disk space wasn't exhausted during recording

### Large File Sizes

**Reduce size by:**
- Lowering FPS (1 FPS is usually sufficient)
- Using condensed recordings for AI analysis
- Implementing regular cleanup
- Compressing older recordings with ffmpeg

## FAQ

**Q: Can I use recordings without saving to disk?**
A: Yes! With `save_recordings=False` (default), the AI still analyzes frames from memory. This is the recommended mode for most users.

**Q: How do I review past activity if recordings aren't saved?**
A: The AI stores analyzed context in the database. You can query past activity using the chat interface even without saved videos.

**Q: Can I save only screenshots but not videos?**
A: Currently, the `save_recordings` flag controls both. You could modify the code to separate these if needed.

**Q: Where is the database stored?**
A: The context database is in `companion_memory.db` and always saved regardless of `save_recordings` setting.

## Support

For issues or questions:
- Check the main README.md
- Review error messages in console output
- Ensure all dependencies are installed
- Check disk space and permissions

---

**Last Updated:** 2025-01-30
**Version:** 1.0
