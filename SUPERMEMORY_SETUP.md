# Supermemory Integration Guide

This guide explains how to use the Supermemory API integration in Ghost Widget for faster, cloud-based context retrieval.

## What is Supermemory?

Supermemory is a universal memory API for AI applications that provides:
- **Fast retrieval**: Sub-400ms latency (10x faster than Zep, 25x faster than Mem0)
- **Semantic search**: Advanced context retrieval using embeddings
- **Cloud storage**: No local database size limits
- **Better accuracy**: Best-in-class precision and recall

## Setup Instructions

### 1. Install Supermemory SDK

```bash
pip install --pre supermemory
```

### 2. Get a Supermemory API Key

1. Visit [https://supermemory.ai/](https://supermemory.ai/)
2. Sign up for an account
3. Get your API key from the dashboard

### 3. Configure the Application

#### Option A: Using the GUI (main.py)

1. Launch the application:
   ```bash
   python main.py
   ```

2. Click on the **Settings** tab
3. Enter your Supermemory API key in the "Supermemory API Key" field
4. Click **Save**

#### Option B: Using Environment Variables

Set the environment variable before running:

**Windows:**
```cmd
set SUPERMEMORY_API_KEY=your_api_key_here
```

**Linux/Mac:**
```bash
export SUPERMEMORY_API_KEY=your_api_key_here
```

#### Option C: Using Command Line Arguments

```bash
python backend.py query --api-key YOUR_GEMINI_KEY --supermemory-api-key YOUR_SUPERMEMORY_KEY --question "What was I working on yesterday?"
```

## How It Works

### Context Storage

When you capture a screenshot, the app:
1. Analyzes it with Gemini Vision
2. Extracts text content
3. **Stores in both**:
   - Local SQLite database (backup/fallback)
   - Supermemory cloud (primary storage)

### Context Retrieval

When you ask a question, the app:
1. **First tries** Supermemory API for fast retrieval
2. **Falls back** to local database if Supermemory is unavailable
3. Returns the most relevant contexts based on semantic similarity

## Command Line Usage

### Capture Mode with Supermemory

```bash
python backend.py capture --api-key YOUR_GEMINI_KEY --supermemory-api-key YOUR_SUPERMEMORY_KEY --interval 60 --watch-dirs ~/Documents ~/Projects
```

### Query Mode with Supermemory

```bash
python backend.py query --api-key YOUR_GEMINI_KEY --supermemory-api-key YOUR_SUPERMEMORY_KEY --question "What files did I edit today?"
```

### Disable Supermemory (Use Local Only)

```bash
python backend.py query --api-key YOUR_GEMINI_KEY --no-supermemory --question "Show me recent contexts"
```

## Advantages of Using Supermemory

### Performance
- ✅ **10x faster** than alternative solutions
- ✅ **Sub-400ms** latency for context retrieval
- ✅ **Scalable** - no local storage limits

### Reliability
- ✅ **Cloud backup** - contexts stored in the cloud
- ✅ **Automatic fallback** - uses local DB if API unavailable
- ✅ **Better search** - advanced semantic similarity

### Features
- ✅ **Cross-device** - access contexts from multiple machines
- ✅ **Better precision** - improved context matching
- ✅ **Unlimited storage** - no local database size concerns

## Fallback Behavior

The application is designed to work seamlessly with or without Supermemory:

| Scenario | Behavior |
|----------|----------|
| Supermemory available | Uses Supermemory for fast retrieval |
| Supermemory unavailable | Falls back to local SQLite database |
| No API key provided | Uses local database only |
| Network issues | Automatically switches to local database |

## Verification

After setup, you should see these messages in the console:

```
✅ Supermemory API initialized successfully!
```

When capturing:
```
[2025-10-17 10:30:45] Context stored in local DB and Supermemory
```

When querying:
```
🔍 Searching Supermemory with query: 'What was I working on?'
✅ Retrieved 10 results from Supermemory
```

## Troubleshooting

### "supermemory package not installed"
```bash
pip install --pre supermemory
```

### "Supermemory API key not provided"
Set the `SUPERMEMORY_API_KEY` environment variable or provide it via GUI/command line.

### "Failed to store in Supermemory"
- Check your internet connection
- Verify your API key is correct
- Check Supermemory service status at [https://supermemory.ai/](https://supermemory.ai/)
- **Note**: Contexts are still saved locally as backup

### Falling back to local database
This is normal behavior when:
- Supermemory service is temporarily unavailable
- Network connectivity issues
- API rate limits reached

## Additional Resources

- [Supermemory Documentation](https://supermemory.ai/docs/)
- [Python SDK Documentation](https://supermemory.ai/docs/memory-api/sdks/python)
- [GitHub Repository](https://github.com/supermemoryai/supermemory)

## Support

For Supermemory-specific issues:
- Email: dhravya@supermemory.com
- Docs: https://docs.supermemory.ai/

For Ghost Widget issues:
- Check the main README.md
- Review console output for error messages
