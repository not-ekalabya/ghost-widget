# Mem0 Graph Memory Integration Guide

This guide explains how to use the Mem0 API with graph memory in Ghost Widget for intelligent, cloud-based context retrieval with per-user memory separation.

## What is Mem0?

Mem0 is a universal memory layer for AI applications that provides:
- **Graph Memory**: Knowledge graph storage with entity relationships
- **Semantic search**: Advanced context retrieval using embeddings
- **Per-user separation**: Individual memory databases for different users
- **Cloud storage**: No local database size limits
- **Multi-modal support**: Vector, key-value, and graph database integration

## Setup Instructions

### 1. Install Mem0

```bash
pip install mem0ai
```

**Note:** The managed Mem0 platform automatically handles graph memory - no additional setup required!

### 2. Get a Mem0 API Key

1. Visit [https://mem0.ai/](https://mem0.ai/)
2. Sign up for an account
3. Get your API key from the dashboard

### 3. Implementation Details

The Mem0 API key should be loaded from the environment:
```python
mem0_api_key = os.environ.get("MEM0_API_KEY")
```

The application uses `MemoryClient` which connects to the **managed Mem0 platform**:
- Graph memory is handled automatically by the platform
- No local graph database setup required
- All storage and retrieval is cloud-based

### 4. Configure the Application

#### Using the GUI (main.py)

1. Launch the application:
   ```bash
   python main.py
   ```

2. Click on the **Settings** tab
3. Set your **User ID** for per-user memory separation
   - This is automatically set based on your authenticated email
   - Format: `email_at_domain_com` (sanitized)
4. Click **Save**

#### Using Command Line Arguments

```bash
python backend.py query --api-key YOUR_GEMINI_KEY --user-id your_user_id --question "What was I working on yesterday?"
```

## How It Works

### Per-User Memory Separation

Each user has their own isolated memory space:
- User ID is derived from authenticated email (e.g., `john_at_example_com`)
- All memories are stored with the `user_id` parameter
- Queries only retrieve memories for the specific user
- Supports anonymous users with unique IDs

### Context Storage

When you capture a screenshot, the app:
1. Analyzes it with Gemini Vision
2. Extracts visual content and context
3. **Stores in both**:
   - Local SQLite database (backup/fallback)
   - Mem0 graph memory (primary storage with user_id)

### Graph Memory Structure

Mem0 stores memories as a knowledge graph:
- **Entities**: People, places, concepts extracted from context
- **Relationships**: Connections between entities
- **Attributes**: Properties and metadata
- **User separation**: All nodes tagged with user_id

### Context Retrieval

When you ask a question, the app:
1. **First tries** Mem0 graph memory with your user_id
2. **Traverses** the knowledge graph for relevant relationships
3. **Falls back** to local database if Mem0 is unavailable
4. Returns the most relevant contexts based on semantic similarity

## Command Line Usage

### Capture Mode with Mem0

```bash
python backend.py capture --api-key YOUR_GEMINI_KEY --user-id john_at_example_com --interval 60 --watch-dirs ~/Documents ~/Projects
```

### Query Mode with Mem0

```bash
python backend.py query --api-key YOUR_GEMINI_KEY --user-id john_at_example_com --question "What files did I edit today?"
```

### Autonomous Mode

```bash
python backend.py autonomous --api-key YOUR_GEMINI_KEY --user-id john_at_example_com --autonomous-interval 180
```

## Advantages of Using Mem0 Graph Memory

### Performance
- ✅ **Graph relationships** - understand connections between memories
- ✅ **Semantic search** - intelligent context retrieval
- ✅ **Scalable** - no local storage limits

### Privacy & Separation
- ✅ **Per-user isolation** - each user has separate memory space
- ✅ **Secure** - memories tagged with user_id
- ✅ **Multi-user support** - perfect for shared systems

### Reliability
- ✅ **Cloud backup** - contexts stored in the cloud
- ✅ **Automatic fallback** - uses local DB if API unavailable
- ✅ **Graph traversal** - finds related memories intelligently

### Features
- ✅ **Cross-device** - access contexts from multiple machines
- ✅ **Better precision** - improved context matching via graph
- ✅ **Unlimited storage** - no local database size concerns
- ✅ **Knowledge graph** - structured relationship storage

## Graph Memory Benefits

Traditional vector memory vs. Graph memory:

| Feature | Vector Only | Graph Memory |
|---------|-------------|--------------|
| Similarity search | ✅ | ✅ |
| Entity relationships | ❌ | ✅ |
| Contextual connections | ❌ | ✅ |
| Multi-hop queries | ❌ | ✅ |
| Knowledge representation | ❌ | ✅ |

## User Authentication Integration

The application automatically manages user IDs:

1. **Google Sign-In**: Uses email as user_id (e.g., `john_at_gmail_com`)
2. **Anonymous**: Uses unique anonymous ID (e.g., `anonymous_abc12345`)
3. **Manual**: Set custom user_id in Settings tab

When you authenticate:
```
✅ Mem0 initialized with graph memory for user: john_at_gmail_com
```

## Verification

After setup, you should see these messages in the console:

```
✅ Mem0 initialized with graph memory for user: john_at_gmail_com
```

When capturing:
```
[2025-10-21 10:30:45] Context stored in local DB and Mem0 graph memory for user 'john_at_gmail_com'
```

When querying:
```
🔍 Searching Mem0 graph memory for user 'john_at_gmail_com' with query: 'What was I working on?'
✅ Retrieved 10 results from Mem0 graph memory
```

## Fallback Behavior

The application is designed to work seamlessly with or without Mem0:

| Scenario | Behavior |
|----------|----------|
| Mem0 available | Uses Mem0 graph memory for retrieval |
| Mem0 unavailable | Falls back to local SQLite database |
| No API key | Uses local database only |
| Network issues | Automatically switches to local database |

## Troubleshooting

### "mem0 package not installed"
```bash
pip install mem0ai
```

### "Failed to store in Mem0"
- Check your internet connection
- Verify your API key is correct in `backend.py`
- Check Mem0 service status at [https://mem0.ai/](https://mem0.ai/)
- **Note**: Contexts are still saved locally as backup

### Falling back to local database
This is normal behavior when:
- Mem0 service is temporarily unavailable
- Network connectivity issues
- API rate limits reached

### Using MemoryClient vs Memory

This implementation uses **MemoryClient** for the managed Mem0 platform:
- **MemoryClient**: Managed platform with automatic graph memory (current implementation)
  - Simple API: just provide api_key
  - Cloud-based storage
  - Graph memory handled automatically

- **Memory**: Open-source self-hosted version (not used here)
  - Requires manual graph database setup
  - More configuration needed
  - For advanced users who want full control

## Additional Resources

- [Mem0 Documentation](https://docs.mem0.ai/)
- [Graph Memory Guide](https://docs.mem0.ai/open-source/graph_memory/overview)
- [Python SDK Quickstart](https://docs.mem0.ai/open-source/python-quickstart)
- [GitHub Repository](https://github.com/mem0ai/mem0)

## Support

For Mem0-specific issues:
- Docs: https://docs.mem0.ai/
- GitHub: https://github.com/mem0ai/mem0

For Ghost Widget issues:
- Check the main README.md
- Review console output for error messages
