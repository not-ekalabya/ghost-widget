# Google Grounding & GUI Visual Indicators - Implementation Plan

##Due to file size limitations, here's the implementation approach:

## Changes Needed

### 1. Backend (backend.py)

**Already completed:**
- ✅ Added `progress_callback` parameter to `__init__`
- ✅ Added `_emit_progress()` helper method
- ✅ Removed DuckDuckGo search functionality
- ✅ Imported Google genai types for grounding

**To complete:**
- Update `query()` method to use Google grounding with the new API
- Add `_emit_progress()` calls throughout query method
- Create model with grounding tool enabled

**Google Grounding Implementation:**
```python
# In query method, replace current model creation with:
from google import genai
from google.genai import types

client = genai.Client(api_key=self.api_key)

# Create grounding tool
grounding_tool = types.Tool(
    google_search=types.GoogleSearch()
)

# Use with generate_content
config = types.GenerateContentConfig(
    tools=[grounding_tool] + self.tools  # Add grounding + file tools
)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=config
)
```

**Progress Callbacks to Add:**
```python
# At each step in query()
self._emit_progress("MEMORY_SEARCH", {
    "status": "Searching",
    "count": count
})

self._emit_progress("MEMORY_RETRIEVED", {
    "status": "Retrieved",
    "count": len(relevant_contexts),
    "contexts": [(timestamp, similarity) for _, timestamp, _, _, _, _, similarity in relevant_contexts]
})

self._emit_progress("AI_PROCESSING", {
    "status": "Processing"
})

self._emit_progress("TOOL_EXECUTE", {
    "tool_name": tool_name,
    "args": tool_args,
    "status": "executing"
})

self._emit_progress("TOOL_COMPLETE", {
    "tool_name": tool_name,
    "status": "success" | "error",
    "result_preview": result[:100]
})

self._emit_progress("GROUNDING_SEARCH", {
    "query": extracted_query,
    "status": "searching"
})

self._emit_progress("ANSWER_READY", {
    "status": "complete"
})
```

### 2. GUI (main.py)

**Create Progress Widget:**
```python
class ProgressWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Progress list
        self.progress_list = QListWidget()
        self.progress_list.setObjectName("progressList")
        layout.addWidget(self.progress_list)

        self.setLayout(layout)

    def add_progress(self, event_type, data):
        """Add progress item with icon and status"""
        if event_type == "MEMORY_SEARCH":
            item = QListWidgetItem(f"🔍 Searching {data['count']} contexts...")
        elif event_type == "MEMORY_RETRIEVED":
            contexts = data.get('contexts', [])
            item = QListWidgetItem(f"📊 Retrieved {data['count']} contexts")
            # Add sub-items for each context
            for ts, sim in contexts[:5]:  # Show top 5
                marker = "📌" if sim == 1.0 else f"🎯 {sim:.3f}"
                sub_item = QListWidgetItem(f"    {marker} {ts}")
                self.progress_list.addItem(sub_item)
        elif event_type == "AI_PROCESSING":
            item = QListWidgetItem("💬 AI processing...")
        elif event_type == "TOOL_EXECUTE":
            tool_name = data['tool_name']
            icon = self._get_tool_icon(tool_name)
            args_str = str(data.get('args', {}))
            item = QListWidgetItem(f"{icon} {tool_name}: {args_str[:50]}...")
        elif event_type == "TOOL_COMPLETE":
            status_icon = "✅" if data['status'] == "success" else "❌"
            item = QListWidgetItem(f"    {status_icon} Complete")
        elif event_type == "GROUNDING_SEARCH":
            item = QListWidgetItem(f"🌐 Web search: {data['query']}")
        elif event_type == "ANSWER_READY":
            item = QListWidgetItem("✨ Answer ready!")
        else:
            item = QListWidgetItem(f"• {event_type}")

        self.progress_list.addItem(item)
        self.progress_list.scrollToBottom()

    def _get_tool_icon(self, tool_name):
        icons = {
            "read_file_as_text": "📄",
            "read_file_with_vision": "📄",
            "list_directory": "📁",
            "search_files": "🔎",
            "get_recent_files": "🕐",
            "get_file_info": "ℹ️"
        }
        return icons.get(tool_name, "🔧")

    def clear(self):
        self.progress_list.clear()
```

**Integrate into OverlayWindow:**
```python
# In OverlayWindow.__init_ui__
# Add to chat tab
self.progress_widget = ProgressWidget()
chat_layout.addWidget(self.progress_widget)

# Add clear button
progress_header = QHBoxLayout()
progress_label = QLabel("PROGRESS")
progress_label.setObjectName("sectionLabel")
progress_header.addWidget(progress_label)

clear_progress_btn = QPushButton("Clear")
clear_progress_btn.setObjectName("textButton")
clear_progress_btn.clicked.connect(self.progress_widget.clear)
progress_header.addWidget(clear_progress_btn)

chat_layout.addLayout(progress_header)
```

**Connect to Backend:**
```python
# In CompanionRunner._instantiate_companion()
def progress_callback(event_type, data):
    # Send to UI through queue
    _from_companion_q.put(("PROGRESS", (event_type, data)))

kwargs = {
    ...
    "progress_callback": progress_callback
}

# In OverlayWindow.poll_companion_queue()
elif typ == "PROGRESS":
    event_type, data = payload
    self.progress_widget.add_progress(event_type, data)
```

### 3. Styling

**Add to main.py styles:**
```python
#progressList {
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 10px;
    color: #D4D4D8;
    padding: 6px;
    font-size: 11px;
    font-family: 'SF Mono', 'Consolas', monospace;
}

#progressList::item {
    padding: 6px 10px;
    border-radius: 4px;
    margin: 2px;
}

#progressList::item:hover {
    background: rgba(255, 255, 255, 0.04);
}
```

## Testing

1. Run the app
2. Ask a question
3. Watch progress widget populate with:
   - Memory search indicator
   - Retrieved contexts with timestamps
   - AI processing indicator
   - File read indicators
   - Web search (grounding) indicators
   - Completion indicator

## Benefits

✅ **Real-time feedback**: See exactly what's happening
✅ **Google grounding**: Built-in web search capability
✅ **Better UX**: Visual progress vs terminal output
✅ **Debugging**: Easy to see where things slow down or fail
✅ **Professional**: Modern app feel

