# Visual Indicators & Web Search Update

This document describes the visual indicators and web search functionality added to the Ghost Widget application.

## Features Added

### 1. Web Search Capability

The model can now search the web using DuckDuckGo to get current information, verify facts, or supplement stored contexts.

**Tool Added:**
- `search_web`: Searches DuckDuckGo and returns titles, URLs, and snippets

**Usage:**
The AI will automatically use web search when:
- Current/recent information is needed
- Facts need to be verified
- The question requires knowledge beyond stored contexts
- Real-time data is requested (weather, news, etc.)

**Dependencies:**
```bash
pip install requests beautifulsoup4
```

### 2. Visual Indicators for Query Processing

When you ask a question, the system now displays a detailed progress view:

#### Step 1: Memory Retrieval
```
============================================================
🤖 PROCESSING YOUR QUESTION
============================================================

🔍 Step 1: Searching through 150 stored contexts...

📊 Step 2: Retrieved 10 relevant contexts:
────────────────────────────────────────────────────────────
  1. [📌 RECENT] 2025-10-17 10:30:45
  2. [🎯 0.892] 2025-10-17 09:15:23
  3. [🎯 0.854] 2025-10-17 08:45:12
  ...
```

**Indicators:**
- 📌 RECENT: Always-included recent contexts
- 🎯 [score]: Semantically similar contexts (higher = more relevant)

#### Step 2: AI Processing
```
────────────────────────────────────────────────────────────
💬 Step 3: Processing with Gemini AI...
────────────────────────────────────────────────────────────
```

#### Step 3: Tool Execution

The system shows detailed progress for each tool used:

**File Operations:**
```
────────────────────────────────────────────────────────────
🔧 Step 4: Executing tools to gather information...
────────────────────────────────────────────────────────────

  📄 [1] Reading file: config.json
      Path: C:\projects\ghost-widget\config.json
      ✅ Complete

  📄 [2] Reading file: backend.py
      Path: C:\projects\ghost-widget\backend.py
      ✅ Complete
```

**Web Searches:**
```
  🌐 [3] Searching web: 'Python 3.12 new features'
      🌐 Searching web: 'Python 3.12 new features'
      ✅ Found 5 results
```

**Other Tools:**
```
  📁 [4] Listing directory: C:\projects\ghost-widget
      ✅ Complete

  🔎 [5] Searching files: *.py
      ✅ Complete

  🕐 [6] Getting files from last 24 hours
      ✅ Complete

  ℹ️  [7] Getting info for: README.md
      ✅ Complete
```

**Error Handling:**
```
  📄 [8] Reading file: nonexistent.txt
      ❌ Failed
```

#### Step 4: Final Answer Generation
```
────────────────────────────────────────────────────────────
✨ Step 5: Generating final answer...
────────────────────────────────────────────────────────────

============================================================
✅ ANSWER READY
============================================================
```

## Visual Indicator Icons

| Icon | Meaning |
|------|---------|
| 🤖 | AI processing |
| 🔍 | Searching/Retrieving |
| 📊 | Retrieved results |
| 💬 | AI thinking |
| 🔧 | Tool execution |
| 📄 | File read operation |
| 🌐 | Web search |
| 📁 | Directory operation |
| 🔎 | File search |
| 🕐 | Time-based query |
| ℹ️ | Information retrieval |
| ✅ | Success |
| ❌ | Error/Failure |
| 🔄 | Processing/In progress |
| ✨ | Final answer generation |
| 📌 | Recent/Important |
| 🎯 | Relevance score |

## Example Output

Here's what you'll see when asking a question:

```
============================================================
🤖 PROCESSING YOUR QUESTION
============================================================

🔍 Step 1: Searching through 47 stored contexts...

📊 Step 2: Retrieved 10 relevant contexts:
────────────────────────────────────────────────────────────
  1. [📌 RECENT] 2025-10-17 14:30:15
  2. [📌 RECENT] 2025-10-17 14:15:22
  3. [📌 RECENT] 2025-10-17 14:00:08
  4. [🎯 0.923] 2025-10-17 13:45:30
  5. [🎯 0.887] 2025-10-17 13:20:11
  ...

────────────────────────────────────────────────────────────
💬 Step 3: Processing with Gemini AI...
────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────
🔧 Step 4: Executing tools to gather information...
────────────────────────────────────────────────────────────

  📄 [1] Reading file: backend.py
      Path: C:\projects\ghost-widget\backend.py
      ✅ Complete

  🌐 [2] Searching web: 'Supermemory API documentation 2025'
      🌐 Searching web: 'Supermemory API documentation 2025'
      ✅ Found 5 results

  🔄 Sending results back to AI for processing...

────────────────────────────────────────────────────────────
✅ Completed 2 tool execution(s)
────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────
✨ Step 5: Generating final answer...
────────────────────────────────────────────────────────────

============================================================
✅ ANSWER READY
============================================================

[Your answer appears here...]
```

## Technical Details

### Web Search Implementation

**Function:** `search_web(query, num_results=5)`

**Features:**
- Uses DuckDuckGo HTML interface (no API key required)
- Returns structured JSON with titles, URLs, snippets
- Configurable result count (1-10)
- 10-second timeout for reliability
- Proper error handling and fallback

**Response Format:**
```json
{
  "query": "Python 3.12 features",
  "num_results": 5,
  "results": [
    {
      "title": "What's New In Python 3.12",
      "url": "https://docs.python.org/3.12/whatsnew/3.12.html",
      "snippet": "Summary of new features...",
      "position": 1
    }
  ]
}
```

### Visual Indicator System

**Location:** `backend.py:1319-1540` (query method)

**Key Features:**
1. **Step-by-step progress tracking**
2. **Tool-specific icons and descriptions**
3. **Success/failure indicators**
4. **Result summaries** (e.g., "Found 5 results")
5. **Clear section dividers**
6. **Numbered tool executions**

## Benefits

✅ **Better User Experience:** Users can see exactly what the AI is doing
✅ **Transparency:** Clear visibility into memory retrieval and tool usage
✅ **Debugging:** Easy to identify where issues occur
✅ **Progress Tracking:** Know when operations take longer
✅ **Web Access:** AI can now access current information from the internet
✅ **Multi-source Answers:** Combines stored contexts + files + web search

## Usage Tips

1. **Ask questions requiring current info:** The AI will automatically search the web
   - "What's the latest version of Python?"
   - "Current weather in New York"
   - "Recent news about AI"

2. **Watch the progress:** Visual indicators help understand what's happening

3. **Check tool execution:** If a file read fails, you'll see the ❌ indicator

4. **Monitor web searches:** See exactly what the AI is searching for

5. **Use for debugging:** Detailed logs help identify issues quickly

## Notes

- Web search requires `requests` and `beautifulsoup4` packages
- Web search uses DuckDuckGo (no API key needed)
- Visual indicators appear in console output (not in GUI yet)
- Tool execution is automatic based on AI's needs
- The AI intelligently decides when to use each tool

## Future Enhancements

Potential improvements for future versions:
- [ ] Add visual indicators to the PyQt GUI
- [ ] Progress bar for long operations
- [ ] Real-time streaming of tool results
- [ ] Tool execution history viewer
- [ ] Configurable verbosity levels
- [ ] Export tool execution logs
