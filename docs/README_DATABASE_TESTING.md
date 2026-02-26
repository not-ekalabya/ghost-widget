# Database Testing Tool

This tool allows you to inspect, query, and manage memories stored in both the SQLite and ChromaDB databases used by Ghost Widget.

## Overview

Ghost Widget uses a dual-database approach for redundancy and performance:

1. **SQLite Database** (`companion_memory.db`):
   - Primary backup storage
   - Simple SQL-based queries
   - Stores context snapshots with embeddings

2. **ChromaDB** (`local_memory_db/`):
   - Vector database for semantic search
   - Temporal-aware memory retrieval
   - High-performance similarity search
   - Creates `chroma.sqlite3` internally

## Installation

Make sure you have all required dependencies:

```bash
pip install chromadb google-generativeai
```

## Usage

### Quick Status Check

```bash
python tests/test_database.py --action status
```

This will show:
- Which databases exist
- Number of memories in each database
- Storage paths and configuration

### Interactive Mode (Recommended)

```bash
python tests/test_database.py --api-key YOUR_GEMINI_API_KEY
```

Or set the API key as an environment variable:

```bash
set GEMINI_API_KEY=your_api_key_here
python tests/test_database.py
```

Interactive mode provides a menu with these options:
1. View SQLite memories
2. View ChromaDB memories
3. Search SQLite (text matching)
4. Search ChromaDB (semantic search)
5. Compare both databases
6. Clear SQLite database
7. Clear ChromaDB database
8. Refresh status

### Command-Line Actions

#### View Memories

```bash
# View SQLite memories
python tests/test_database.py --action view-sqlite --limit 20

# View ChromaDB memories (requires API key)
python tests/test_database.py --action view-chromadb --limit 20 --api-key YOUR_KEY
```

#### Search Memories

```bash
# Text search in SQLite
python tests/test_database.py --action search-sqlite --query "python code" --limit 10

# Semantic search in ChromaDB (requires API key)
python tests/test_database.py --action search-chromadb --query "what was I working on?" --limit 10 --api-key YOUR_KEY
```

#### Clear Databases

```bash
# Clear SQLite (will ask for confirmation)
python tests/test_database.py --action clear-sqlite

# Clear ChromaDB (will ask for confirmation)
python tests/test_database.py --action clear-chromadb --api-key YOUR_KEY
```

### Custom Paths

If your databases are in non-default locations:

```bash
python tests/test_database.py \
  --sqlite-db "path/to/companion_memory.db" \
  --chromadb "path/to/local_memory_db" \
  --user-id "your_user_id" \
  --action status
```

## Troubleshooting

### "ChromaDB not available" message

This means either:
1. The `chromadb` package is not installed: `pip install chromadb`
2. No API key was provided for ChromaDB operations
3. The `local_memory_db` directory doesn't exist yet (will be created when first memory is stored)

### "SQLite database not found"

The `companion_memory.db` file hasn't been created yet. This is normal if:
- You just started using Ghost Widget
- You deleted the database to start fresh

The database will be created automatically when the first context is captured.

### Memories not appearing in ChromaDB

Check the console output when running Ghost Widget. If you see:
- `⚠️ Failed to initialize local memory` - ChromaDB initialization failed
- `⚠️ ChromaDB not available, storing to SQLite only` - Memories are only being saved to SQLite

Common causes:
1. `chromadb` or `google-generativeai` packages not installed
2. Invalid API key
3. Disk space or permission issues in the `local_memory_db` directory

## Database Schema

### SQLite (`companion_memory.db`)

Table: `context_snapshots`
- `id`: Primary key
- `timestamp`: When the context was captured
- `screenshot_path`: Path to saved screenshot (if any)
- `description`: Text description of the context
- `active_files`: JSON array of recently accessed files
- `open_applications`: JSON array of running applications
- `tags`: JSON array of tags (for AI-stored memories)
- `embedding`: Binary blob of the embedding vector
- `created_at`: Creation timestamp
- `screen_text`: Extracted text from screen

### ChromaDB (`local_memory_db/`)

Collections: `memories_{user_id}`
- Documents: Full text content of memories
- Embeddings: 768-dimensional vectors from Google's text-embedding-004
- Metadata:
  - `user_id`: User identifier
  - `timestamp`: When memory was created
  - `context_id`: Reference to SQLite record (for screen captures)
  - `summary`: Brief summary (for AI-stored memories)
  - `importance`: Priority level (low/medium/high)
  - `tags`: Associated tags
  - `type`: "ai_stored" or "screen_capture"

## Examples

### Check if memories are being stored

```bash
python tests/test_database.py --action status
```

Expected output:
```
DATABASE STATUS REPORT
======================================================================

📁 Database Files:
   SQLite DB (companion_memory.db): ✓ EXISTS
   ChromaDB Dir (local_memory_db): ✓ EXISTS
   ChromaDB Files:
      - local_memory_db\chroma.sqlite3

📊 SQLite Database:
   Tables: context_snapshots
   context_snapshots: 42 records

📊 ChromaDB Database:
   Total memories: 42
   User ID: default_user
   Storage path: C:\projects\ghost-widget\local_memory_db
   Temporal decay: 30 days
```

### Find specific memories

```bash
# Interactive search
python tests/test_database.py
# Then select option 4 and enter your query
```

### Compare database sync

```bash
python tests/test_database.py
# Select option 5 to see if both databases have the same count
```

## Advanced Usage

### Programmatic Access

You can also import and use the `DatabaseInspector` class in your own scripts:

```python
from tests.test_database import DatabaseInspector

inspector = DatabaseInspector(
    sqlite_db_path="companion_memory.db",
    chromadb_path="local_memory_db",
    user_id="default_user",
    api_key="your_api_key"
)

# Get stats
sqlite_stats = inspector.get_sqlite_stats()
chromadb_stats = inspector.get_chromadb_stats()

# View memories
memories = inspector.view_all_chromadb_memories(limit=10)

# Search
results = inspector.search_chromadb_memories("what was I coding?", limit=5)
```

## Support

If you encounter issues with the database testing tool, please check:
1. All dependencies are installed
2. API key is valid (for ChromaDB operations)
3. You have read/write permissions in the database directories

For Ghost Widget support, see the main README.md file.
