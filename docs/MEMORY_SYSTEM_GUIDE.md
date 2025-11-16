# Ghost Widget Memory System - Tool Calls Guide

## Overview

The Ghost Widget now has a comprehensive memory system that allows the AI to store, retrieve, and manage contextual information during chat interactions using tool calls. The system uses FAISS for local, privacy-focused vector storage with semantic search and temporal awareness.

## Available Memory Tool Calls

### 1. `store_memory`
**Purpose:** Store important information to long-term memory

**Parameters:**
- `content` (string, required): Detailed content to store
- `summary` (string, required): Brief one-sentence summary
- `importance` (string, required): Level of importance - "low", "medium", or "high"
- `tags` (array, optional): Tags for categorization (e.g., ['coding', 'python'])

**Example:**
```json
{
  "content": "User was working on a Python ML project using TensorFlow",
  "summary": "Working on ML project with TensorFlow",
  "importance": "high",
  "tags": ["python", "machine-learning", "tensorflow"]
}
```

**Returns:**
```json
{
  "success": true,
  "message": "Memory stored successfully: Working on ML project with TensorFlow",
  "timestamp": "2025-11-16 10:45:42",
  "user_id": "test_user",
  "memory_id": "mem_42",
  "storage_locations": ["ChromaDB"]
}
```

---

### 2. `search_memories`
**Purpose:** Search stored memories using semantic search with temporal awareness

**Parameters:**
- `query` (string, required): Search query
- `top_k` (integer, optional): Number of results to return (default: 5)
- `filter_tags` (array, optional): Filter by specific tags

**Example:**
```json
{
  "query": "machine learning Python",
  "top_k": 3
}
```

**Returns:**
```json
{
  "success": true,
  "count": 3,
  "query": "machine learning Python",
  "memories": [
    {
      "rank": 1,
      "id": "mem_42",
      "content": "[Memory content here]",
      "summary": "Working on ML project with TensorFlow",
      "importance": "high",
      "tags": ["python", "machine-learning", "tensorflow"],
      "created_at": "2025-11-16T10:45:42.123456",
      "temporal_score": 0.790,
      "base_similarity": 0.856
    }
  ]
}
```

---

### 3. `get_recent_memories`
**Purpose:** Get the most recent memories without semantic search

**Parameters:**
- `limit` (integer, optional): Number of recent memories (default: 10)

**Example:**
```json
{
  "limit": 5
}
```

**Returns:**
```json
{
  "success": true,
  "count": 5,
  "memories": [
    {
      "rank": 1,
      "id": "mem_43",
      "content": "[Memory content]",
      "summary": "Learning React hooks",
      "importance": "medium",
      "tags": ["javascript", "react"],
      "created_at": "2025-11-16T10:45:43.789012"
    }
  ]
}
```

---

### 4. `get_memory_stats`
**Purpose:** Get statistics about stored memories

**Parameters:** None

**Example:**
```json
{}
```

**Returns:**
```json
{
  "success": true,
  "stats": {
    "total_memories": 44,
    "user_id": "test_user",
    "storage_path": "C:\\projects\\ghost-widget\\faiss_memory_db",
    "temporal_decay_days": 30,
    "storage_type": "FAISS (Local, Privacy-Focused)"
  }
}
```

---

### 5. `clear_memories`
**Purpose:** Clear all stored memories for the current user (use with caution)

**Parameters:**
- `confirm` (boolean, required): Must be `true` to confirm deletion

**Example:**
```json
{
  "confirm": true
}
```

**Returns:**
```json
{
  "success": true,
  "message": "All memories cleared for user: test_user"
}
```

---

## Usage During Chat

### How the AI Uses Memory Tools

1. **Automatic Storage:** The AI automatically stores important context from screen captures using `store_memory`

2. **Context Retrieval:** When answering questions, the AI can use `search_memories` to recall relevant past information

3. **Recent Context:** The AI can use `get_recent_memories` to see what was recently stored

4. **Memory Management:** Users can ask the AI to check memory stats or clear memories

### Example Chat Interactions

**User:** "Store the fact that I'm learning React hooks"

**AI:** Uses `store_memory` tool:
```json
{
  "content": "User is learning React hooks for frontend development",
  "summary": "Learning React hooks",
  "importance": "medium",
  "tags": ["javascript", "react", "learning"]
}
```

---

**User:** "What was I working on last week related to Python?"

**AI:** Uses `search_memories` tool:
```json
{
  "query": "Python work projects coding",
  "top_k": 5
}
```

Then synthesizes the results into a natural response.

---

**User:** "How many things have you remembered about me?"

**AI:** Uses `get_memory_stats` tool and reports back the total count and details.

---

## Technical Details

### Storage Backend
- **Technology:** FAISS (Facebook AI Similarity Search)
- **Embeddings:** Google text-embedding-004 (768 dimensions)
- **Location:** Local disk (`faiss_memory_db/` directory)
- **Privacy:** All data stored locally, no cloud storage
- **Note:** The system previously used ChromaDB but was migrated to FAISS for better Windows compatibility and stability

### Temporal Awareness
Memories are scored using both:
- **Semantic Similarity:** How relevant the content is to the query
- **Temporal Score:** More recent memories are weighted higher
- **Combined Score:** 70% semantic + 30% temporal

Temporal decay formula:
```
temporal_multiplier = exp(-decay_rate × days_old)
decay_rate = 2.0 / temporal_decay_days
```

### Thread Safety
- All FAISS operations use RLock for thread safety
- Safe for concurrent access from GUI and background threads

## Testing

Run the included test script:
```bash
python test_memory_tools.py
```

This tests:
- Memory storage
- Memory search
- Recent memory retrieval
- Statistics retrieval
- JSON serialization

## Integration Points

### In `backend.py`

1. **Tool Definitions:**
   - Line 302-390: Gemini tool definitions
   - Line 4978-5069: Claude tool definitions

2. **Tool Implementations:**
   - Line 2451-2703: Memory function implementations

3. **Tool Execution Mapping:**
   - Line 3207-3218: Tool execution dictionary

4. **Logging:**
   - Line 4434-4446: Gemini tool call logging
   - Line 4785-4797: Claude tool call logging

## Error Handling

All memory tools return JSON with error information:
```json
{
  "success": false,
  "error": "Error description here"
}
```

Common errors:
- Memory system not initialized
- Search query failed
- JSON serialization issues (handled by converting numpy types and protobuf RepeatedComposite)

### Fixed Issues
1. **Numpy float32 serialization:** Automatically converts numpy floats to Python floats for JSON compatibility
2. **Protobuf RepeatedComposite:** Converts Gemini's protobuf tag lists to Python lists before JSON serialization
3. **Windows Unicode:** Test script includes UTF-8 encoding fix for Windows console

## Best Practices

1. **Storage Granularity:** Store meaningful activities, not every screen change
2. **Tagging:** Use consistent, descriptive tags for better retrieval
3. **Importance Levels:** Reserve "high" for truly important information
4. **Search Queries:** Use natural language queries for best semantic matching
5. **Regular Stats Check:** Monitor memory count to understand what's being stored

## Future Enhancements

Potential improvements:
- Tag-based filtering in search
- Memory editing/updating
- Bulk export/import
- Memory expiration by age
- Custom importance weighting
- Memory compression for long-term storage
