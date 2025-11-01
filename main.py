#!/usr/bin/env python3
"""
Modern Overlay app that wraps Ghost Widget from main.py

Features:
- Floating translucent panel (draggable) always on top
- Modern, sleek dark mode design with glassmorphism
- Start / Stop recording
- Ask questions (textbox) and show responses
- Edit & save API key, interval, watched directories to config.json
- Runs BackgroundCompanion in a daemon thread and interacts with it, with graceful fallbacks
"""

import sys
import os
import json
import threading
import time
import re
import subprocess
from pathlib import Path
from queue import Queue, Empty
from html import escape
import datetime

# Try importing markdown library
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

# Import BackgroundCompanion from user's main.py (must be in same folder)
try:
    from backend import BackgroundCompanion
except Exception as e:
    BackgroundCompanion = None
    import traceback
    _import_error = traceback.format_exc()

# Import Firebase Auth
try:
    from firebase_auth import FirebaseAuth
    FIREBASE_AVAILABLE = True
except Exception as e:
    FIREBASE_AVAILABLE = False
    _firebase_import_error = str(e)

# Import GitHub Auth
try:
    from github_auth import get_github_auth
    GITHUB_AVAILABLE = True
except Exception as e:
    GITHUB_AVAILABLE = False
    _github_import_error = str(e)

# Import Firestore Chat Manager
try:
    from firestore_chat import FirestoreChatManager
    FIRESTORE_CHAT_AVAILABLE = True
except Exception as e:
    FIRESTORE_CHAT_AVAILABLE = False
    _firestore_chat_import_error = str(e)

# Import Auto-updater
try:
    from updater import UpdateChecker, check_for_updates_background
    from version import __version__
    UPDATER_AVAILABLE = True
except Exception as e:
    UPDATER_AVAILABLE = False
    __version__ = "1.0.0"
    _updater_import_error = str(e)

USE_PYQT6 = True
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSpinBox,
    QGraphicsDropShadowEffect, QTabWidget, QComboBox, QScrollArea, QFrame, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, pyqtSignal, QObject, QPropertyAnimation, QEasingCurve, QMimeData
from PyQt6.QtGui import QFont, QAction, QColor

from pynput import keyboard

HOTKEY_COMBO = "<ctrl>+<alt>+`"   # you can change this to whatever you want

_hotkey_queue = Queue()

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def convert_markdown_to_html(text):
    """Convert markdown text to HTML with proper styling."""
    if MARKDOWN_AVAILABLE:
        # Use markdown library if available
        html = markdown.markdown(
            text,
            extensions=['fenced_code', 'codehilite', 'tables', 'nl2br']
        )
    else:
        # Lightweight markdown converter
        html = escape(text)

        # Code blocks (```language\n...\n```)
        html = re.sub(
            r'```([\w]*)?\n([\s\S]*?)```',
            r'<pre style="background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; overflow-x: auto; margin: 8px 0;"><code>\2</code></pre>',
            html
        )

        # Inline code (`code`)
        html = re.sub(
            r'`([^`]+)`',
            r'<code style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 13px;">\1</code>',
            html
        )

        # Headers
        html = re.sub(r'^### (.+)$', r'<h3 style="color: #FAFAFA; font-size: 16px; font-weight: 600; margin: 12px 0 8px 0;">\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2 style="color: #FAFAFA; font-size: 18px; font-weight: 600; margin: 14px 0 10px 0;">\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1 style="color: #FAFAFA; font-size: 20px; font-weight: 700; margin: 16px 0 12px 0;">\1</h1>', html, flags=re.MULTILINE)

        # Bold (**text** or __text__)
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong style="font-weight: 600; color: #FAFAFA;">\1</strong>', html)
        html = re.sub(r'__(.+?)__', r'<strong style="font-weight: 600; color: #FAFAFA;">\1</strong>', html)

        # Italic (*text* or _text_)
        html = re.sub(r'\*(.+?)\*', r'<em style="font-style: italic; color: #E4E4E7;">\1</em>', html)
        html = re.sub(r'_(.+?)_', r'<em style="font-style: italic; color: #E4E4E7;">\1</em>', html)

        # Links [text](url)
        html = re.sub(
            r'\[([^\]]+)\]\(([^\)]+)\)',
            r'<a href="\2" style="color: #60A5FA; text-decoration: underline;">\1</a>',
            html
        )

        # Unordered lists
        html = re.sub(r'^[\*\-] (.+)$', r'<li style="margin-left: 20px; margin-bottom: 4px;">\1</li>', html, flags=re.MULTILINE)

        # Ordered lists
        html = re.sub(r'^\d+\. (.+)$', r'<li style="margin-left: 20px; margin-bottom: 4px;">\1</li>', html, flags=re.MULTILINE)

        # Blockquotes
        html = re.sub(
            r'^&gt; (.+)$',
            r'<blockquote style="border-left: 3px solid rgba(255,255,255,0.2); padding-left: 12px; margin: 8px 0; color: #A1A1AA;">\1</blockquote>',
            html,
            flags=re.MULTILINE
        )

        # Line breaks
        html = html.replace('\n', '<br>')

    return html

class MarkdownTextEdit(QTextEdit):
    """Custom QTextEdit that preserves markdown format when copying."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.markdown_content = []  # Store markdown text for each message

    def add_markdown_message(self, markdown_text, html_text):
        """Add a message with both markdown and HTML versions."""
        self.markdown_content.append(markdown_text)
        self.append(html_text)

    def clear_messages(self):
        """Clear all messages."""
        self.markdown_content = []
        self.clear()

    def createMimeData(self):
        """Override to provide markdown text when copying."""
        mime = QMimeData()
        # Provide the full markdown content as plain text
        markdown_text = "\n\n---\n\n".join(self.markdown_content)
        mime.setText(markdown_text)
        return mime

def format_progress_html(event_type, data):
    """Format progress event as HTML for display in response area"""
    icon_map = {
        "read_file_as_text": "📄",
        "read_file_with_vision": "📄",
        "list_directory": "📁",
        "search_files": "🔎",
        "get_recent_files": "🕐",
        "get_file_info": "ℹ️"
    }

    if event_type == "MEMORY_SEARCH":
        return f"<span style='color: #71717A; font-size: 11px;'>🔍 Searching {data['count']} contexts...</span>"
    elif event_type == "MEMORY_RETRIEVED":
        contexts = data.get('contexts', [])
        html = f"<span style='color: #10B981; font-size: 11px;'>📊 Retrieved {data['count']} contexts</span><br>"
        # Add sub-items for top contexts
        for ts, sim in contexts[:3]:  # Show top 3
            marker = "📌" if sim == 1.0 else f"🎯 {sim:.3f}"
            html += f"<span style='color: #52525B; font-size: 10px; margin-left: 20px;'>{marker} {ts}</span><br>"
        return html
    elif event_type == "AI_PROCESSING":
        return f"<span style='color: #60A5FA; font-size: 11px;'>💬 Ghost processing...</span>"
    elif event_type == "TOOL_EXECUTE":
        tool_name = data['tool_name']
        icon = icon_map.get(tool_name, "🔧")
        # Handle web search specially
        if tool_name == "search_web":
            query = data.get('args', {}).get('query', '')
            return f"<span style='color: #60A5FA; font-size: 11px;'>🌐 Searching web: '{escape(query[:50])}'</span>"
        # Truncate long paths
        elif 'file_path' in data.get('args', {}):
            file_path = data['args']['file_path']
            file_name = Path(file_path).name if file_path else "unknown"
            return f"<span style='color: #A1A1AA; font-size: 11px;'>{icon} {tool_name}: {escape(file_name)}</span>"
        else:
            args_str = str(data.get('args', {}))[:30]
            return f"<span style='color: #A1A1AA; font-size: 11px;'>{icon} {tool_name}: {escape(args_str)}...</span>"
    elif event_type == "TOOL_COMPLETE":
        status_icon = "✅" if data['status'] == "success" else "❌"
        color = "#10B981" if data['status'] == "success" else "#EF4444"
        return f"<span style='color: {color}; font-size: 10px; margin-left: 20px;'>{status_icon} Complete</span>"
    elif event_type == "GROUNDING_SEARCH":
        return f"<span style='color: #60A5FA; font-size: 11px;'>🌐 Web search used</span>"
    elif event_type == "ANSWER_READY":
        return f"<span style='color: #10B981; font-size: 11px; font-weight: 600;'>✨ Answer ready!</span>"
    else:
        return f"<span style='color: #71717A; font-size: 11px;'>• {event_type}</span>"


def hotkey_listener():
    """Global hotkey listener thread that sends toggle events."""
    def on_activate():
        _hotkey_queue.put(("TOGGLE_VISIBILITY", time.time()))

    with keyboard.GlobalHotKeys({HOTKEY_COMBO: on_activate}) as h:
        h.join()

CONFIG_PATH = Path.home() / ".background_companion_overlay_config.json"

# Thread-safe queues for communicating with companion thread
_to_companion_q = Queue()
_from_companion_q = Queue()


class CompanionRunner(threading.Thread):
    """
    Thread wrapper that instantiates BackgroundCompanion and provides run/stop/ask wrappers.
    It will attempt to call common method names if present.
    """

    def __init__(self, config):
        super().__init__(daemon=True, name="CompanionRunner")
        self.config = config.copy()
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self.companion = None
        self.last_error = None

    def _instantiate_companion(self):
        if BackgroundCompanion is None:
            raise RuntimeError("Couldn't import BackgroundCompanion from main.py.\n" + _import_error)

        # 🔑 Hardcoded API key – replace this string with your real one
        HARD_CODED_API_KEY = "AIzaSyBY6rQz-TCRenrrdXv2uKbE4GTbgHQbLuk"

        # Set environment variable too, just in case main.py reads it from os.environ
        os.environ["GOOGLE_API_KEY"] = HARD_CODED_API_KEY
        os.environ["GEMINI_API_KEY"] = HARD_CODED_API_KEY

        # Progress callback to send progress updates to GUI
        def progress_callback(event_type, data):
            _from_companion_q.put(("PROGRESS", (event_type, data)))

        # Get user_id from config (will be set by auth system)
        user_id = self.config.get("user_id", "default_user")

        # Pass directly to the class
        kwargs = {
            "api_key": HARD_CODED_API_KEY,
            "capture_interval": self.config.get("interval", 10),  # Kept for backward compatibility
            "recording_fps": self.config.get("fps", 1),
            "analysis_interval": self.config.get("analysis_interval", 40),
            "watch_dirs": self.config.get("watch_dirs", []),
            "always_recent": self.config.get("always_recent", 3),
            "user_id": user_id,
            "progress_callback": progress_callback,
            "qa_model": self.config.get("qa_model", "gemini")
        }

        return BackgroundCompanion(**kwargs)

    def run(self):
        try:
            self.companion = self._instantiate_companion()
            self._ready.set()
        except Exception as e:
            self.last_error = str(e)
            self._ready.set()
            # Send error to UI
            _from_companion_q.put(("ERROR", f"Failed to instantiate BackgroundCompanion: {e}"))
            return

        # If companion has a start method, don't auto-start here – let UI control it.
        # Listen for commands from UI
        while not self._stop_event.is_set():
            try:
                cmd, payload = _to_companion_q.get(timeout=0.2)
            except Empty:
                continue

            if cmd == "START":
                # Try to call common methods: start() or run() or loop()
                success, msg = self._call_start()
                _from_companion_q.put(("STARTED" if success else "ERROR", msg))
            elif cmd == "STOP":
                success, msg = self._call_stop()
                _from_companion_q.put(("STOPPED" if success else "ERROR", msg))
            elif cmd == "ASK":
                # Handle both old string format and new dict format
                if isinstance(payload, dict):
                    question = payload.get("question", "")
                    guidance_mode = payload.get("guidance_mode", False)
                else:
                    question = payload
                    guidance_mode = False
                resp = self._call_ask(question, guidance_mode)
                _from_companion_q.put(("RESPONSE", resp))
            elif cmd == "GET_MEMORIES":
                # Get all memories from backend
                memories = self._get_memories()
                _from_companion_q.put(("MEMORIES_LIST", memories))
            elif cmd == "SEARCH_MEMORIES":
                # Search memories by query
                query = payload
                memories = self._search_memories(query)
                _from_companion_q.put(("SEARCH_RESULTS", memories))
            elif cmd == "DELETE_MEMORY":
                # Delete a memory by ID
                memory_id = payload
                success = self._delete_memory(memory_id)
                _from_companion_q.put(("DELETE_SUCCESS", success))
            elif cmd == "UPDATE_CONFIG":
                new_conf = payload or {}
                self._update_config(new_conf)
                _from_companion_q.put(("CONFIG_UPDATED", "config applied"))
            elif cmd == "SHUTDOWN":
                # attempt graceful stop
                self._call_stop()
                self._stop_event.set()
                break

    def _call_start(self):
        if not self.companion:
            return False, "Companion not instantiated."
        # Try typical names
        for method_name in ("start", "run", "begin"):
            if hasattr(self.companion, method_name):
                try:
                    m = getattr(self.companion, method_name)
                    # If method is blocking, run it in a dedicated thread to keep this runner responsive.
                    if callable(m):
                        thr = threading.Thread(target=m, daemon=True, name="CompanionInternalStart")
                        thr.start()
                        return True, f"Called {method_name}() in background thread."
                except Exception as e:
                    return False, f"Exception when calling {method_name}(): {e}"
        # If no start-like method, maybe it has capture_loop() non-blocking
        if hasattr(self.companion, "capture_once"):
            try:
                self.companion.capture_once()
                return True, "Called capture_once() (one-shot)."
            except Exception as e:
                return False, f"Exception calling capture_once(): {e}"
        return False, "No recognized start method on BackgroundCompanion."

    def _call_stop(self):
        if not self.companion:
            return False, "Companion not instantiated."
        # Try common names
        for method_name in ("stop", "shutdown", "close", "terminate"):
            if hasattr(self.companion, method_name):
                try:
                    getattr(self.companion, method_name)()
                    return True, f"Called {method_name}()."
                except Exception as e:
                    return False, f"Exception when calling {method_name}(): {e}"
        # Try toggling a boolean attribute 'running'
        if hasattr(self.companion, "running"):
            try:
                setattr(self.companion, "running", False)
                return True, "Set companion.running = False"
            except Exception as e:
                return False, f"Exception setting running flag: {e}"
        # If none exists: can't reliably stop
        return False, "No recognized stop method/flag on BackgroundCompanion."

    def _call_ask(self, question: str, guidance_mode: bool = False):
        if not self.companion:
            return "Companion not instantiated."
        # Try expected names: ask, query, ask_gemini, send_prompt
        for method_name in ("ask", "query", "ask_gemini", "send_prompt", "chat"):
            if hasattr(self.companion, method_name):
                try:
                        # Check if method accepts guidance_mode parameter
                        import inspect
                        sig = inspect.signature(getattr(self.companion, method_name))
                        if 'guidance_mode' in sig.parameters:
                            result = getattr(self.companion, method_name)(question, guidance_mode=guidance_mode)
                        else:
                            result = getattr(self.companion, method_name)(question)
                        # If backend returns a structured response (dict with display+gemini_raw), forward it
                        return result
                except Exception as e:
                    return f"Error calling {method_name}(): {e}"
        # If companion exposes a 'client' or 'model' attribute, try to call it
        if hasattr(self.companion, "client") and hasattr(self.companion.client, "send"):
            try:
                return self.companion.client.send(question)
            except Exception as e:
                return f"Error sending via companion.client.send(): {e}"
        return "No ask/query method found on BackgroundCompanion."

    def _update_config(self, new_conf: dict):
        # update runtime config and if companion supports runtime changes, apply them
        self.config.update(new_conf)
        # attempt to set attributes on companion if present
        if self.companion:
            for k, v in new_conf.items():
                if hasattr(self.companion, k):
                    try:
                        setattr(self.companion, k, v)
                        # Special handling for user_id changes - log it
                        if k == "user_id":
                            print(f"🔄 Updated companion user_id to: {v}")
                    except Exception:
                        pass

    def _get_memories(self):
        """Get all memories from the companion's mem0 client"""
        if not self.companion:
            return []

        try:
            # Check if companion has mem0_client
            if hasattr(self.companion, 'mem0_client') and self.companion.mem0_client:
                user_id = getattr(self.companion, 'user_id', 'default_user')
                # Get all memories for this user - mem0 API v2 requires filters parameter
                filters = {"user_id": user_id}
                result = self.companion.mem0_client.get_all(filters=filters)

                # mem0 returns a dict with 'results' key containing list of memories
                if isinstance(result, dict) and 'results' in result:
                    return result['results']
                elif isinstance(result, list):
                    return result
                else:
                    return []
            else:
                print("⚠️ mem0_client not available")
                return []
        except Exception as e:
            print(f"Error getting memories: {e}")
            return []

    def _search_memories(self, query: str):
        """Search memories using mem0 search functionality"""
        if not self.companion:
            return []

        try:
            # Check if companion has mem0_client
            if hasattr(self.companion, 'mem0_client') and self.companion.mem0_client:
                user_id = getattr(self.companion, 'user_id', 'default_user')
                # Search memories for this user - mem0 API requires filters parameter
                filters = {"user_id": user_id}
                result = self.companion.mem0_client.search(query=query, filters=filters, limit=50)

                # mem0 returns a dict with 'results' key containing list of memories
                if isinstance(result, dict) and 'results' in result:
                    return result['results']
                elif isinstance(result, list):
                    return result
                else:
                    return []
            else:
                print("⚠️ mem0_client not available")
                return []
        except Exception as e:
            print(f"Error searching memories: {e}")
            return []

    def _delete_memory(self, memory_id: str):
        """Delete a memory by ID"""
        if not self.companion:
            return False

        try:
            # Check if companion has mem0_client
            if hasattr(self.companion, 'mem0_client') and self.companion.mem0_client:
                # Delete the memory
                self.companion.mem0_client.delete(memory_id)
                print(f"✅ Deleted memory: {memory_id}")
                return True
            else:
                print("⚠️ mem0_client not available")
                return False
        except Exception as e:
            print(f"Error deleting memory: {e}")
            return False


# ---------- Qt UI components ----------
class Signals(QObject):
    # simple signal container
    log = pyqtSignal(str)
    status = pyqtSignal(str)
    response = pyqtSignal(str)
    config_saved = pyqtSignal()
    auth_update = pyqtSignal(dict)  # Signal for auth UI updates
    auth_clear = pyqtSignal()  # Signal to clear auth UI


class OverlayWindow(QWidget):
    def __init__(self, config):
        super().__init__(flags=Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.signals = Signals()
        self.signals.log.connect(self.append_log)
        self.signals.status.connect(self.set_status)
        self.signals.response.connect(self.append_response)
        self.signals.config_saved.connect(self.on_config_saved)
        self.signals.auth_update.connect(self._update_auth_ui)
        self.signals.auth_clear.connect(self._clear_auth_ui)

        self.config = config
        self.runner = CompanionRunner(self.config)
        self.runner.start()  # instantiate companion immediately in thread (non-blocking)

        self._drag_pos = None
        self._is_recording = False

        # Firebase Auth instance
        self.firebase_auth = None
        self.auth_refresh_timer = None
        self._init_firebase_auth()

        # GitHub Auth instance
        self.github_auth = None
        self._init_github_auth()

        # Firestore Chat Manager instance
        self.chat_manager = None
        self._init_chat_manager()

        # Track current question for saving to Firestore
        self.current_question = None

        # Store conversation context for continuing chats
        self.conversation_context = None

        # Track current conversation session for continuous chat
        self.current_session = {
            "messages": [],  # List of {question, response} dicts
            "started_at": None,
            "last_document_id": None
        }

        self.init_ui()
        self.start_polling_companion_queue()
        self.start_auth_token_refresh_timer()

        # Check for updates on startup (in background)
        if UPDATER_AVAILABLE:
            self._check_for_updates_on_startup()

    def _init_firebase_auth(self):
        """Initialize Firebase Auth if config file exists"""
        if not FIREBASE_AVAILABLE:
            return

        try:
            # Use embedded Firebase configuration to avoid external files
            embedded_firebase_config = {
              "apiKey": "AIzaSyBsig0QxBmVelZQwef23-MoTFdeuZM5P-4",
              "authDomain": "ghost-widget-7000.firebaseapp.com",
              "projectId": "ghost-widget-7000",
              "databaseURL": "https://ghost-widget-7000-default-rtdb.firebaseio.com/",
              "storageBucket": "ghost-widget-7000.firebasestorage.app",
              "google_client_id": "816342083028-te98svps0mjo5230g3aasfipt8qr824g.apps.googleusercontent.com",
              "google_client_secret": "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",
              "messagingSenderId": "816342083028",
              "appId": "1:816342083028:web:0e0d8aa40d66bf858f2241",
              "measurementId": "G-XGLGL9E2TJ"
            }

            self.firebase_auth = FirebaseAuth(config=embedded_firebase_config, persist_auth=True)
            print("Firebase Auth initialized successfully")

            # Check if user is already authenticated from previous session
            if self.firebase_auth.is_authenticated():
                user_data = self.firebase_auth.get_current_user()
                if user_data:
                    # Update UI to show authenticated state
                    print(f"✅ Auto-restored session for: {self.firebase_auth.get_user_email()}")
                    # We'll update the UI after init_ui is called
                    self._pending_auth_restore = user_data
                else:
                    self._pending_auth_restore = None
            else:
                self._pending_auth_restore = None
        except Exception as e:
            print(f"Failed to initialize Firebase Auth: {e}")
            self._pending_auth_restore = None

    def _init_github_auth(self):
        """Initialize GitHub Auth"""
        if not GITHUB_AVAILABLE:
            self._pending_github_restore = None
            return

        try:
            self.github_auth = get_github_auth()
            if self.github_auth and self.github_auth.is_authenticated():
                user_info = self.github_auth.get_user_info()
                if user_info:
                    print(f"✅ GitHub: Auto-restored session for: {user_info['login']}")
                    # Store for UI update after init_ui() is called
                    self._pending_github_restore = user_info
                else:
                    self._pending_github_restore = None
            else:
                self._pending_github_restore = None
        except Exception as e:
            print(f"Failed to initialize GitHub Auth: {e}")
            self._pending_github_restore = None

    def _init_chat_manager(self):
        """Initialize Firestore Chat Manager"""
        if not FIRESTORE_CHAT_AVAILABLE:
            print("Firestore Chat Manager not available")
            return

        try:
            self.chat_manager = FirestoreChatManager()
            if self.chat_manager.is_available():
                print("✅ Firestore Chat Manager initialized successfully")
            else:
                print("⚠️ Firestore Chat Manager initialized but not available")
        except Exception as e:
            print(f"❌ Failed to initialize Firestore Chat Manager: {e}")
            import traceback
            traceback.print_exc()

    def update_github_ui_state(self, username):
        """Update GitHub UI to show authenticated state"""
        if hasattr(self, 'github_signin_btn') and hasattr(self, 'github_user_lbl'):
            self.github_signin_btn.setEnabled(False)
            self.github_signin_btn.setText("✓ Connected to GitHub")
            self.github_user_lbl.setText(f"Connected as: {username}")
            self.github_user_lbl.setStyleSheet("color: #10B981; font-size: 11px; margin-top: 8px;")

    def _save_chat_to_firestore(self, response_text: str):
        """Add message to current session (continuous chat in one conversation)"""
        # Check if we have all required components
        if not self.chat_manager or not self.chat_manager.is_available():
            print("⚠️ Chat manager not available, skipping Firestore save")
            return

        if not self.firebase_auth or not self.firebase_auth.is_authenticated():
            print("⚠️ User not authenticated, skipping Firestore save")
            return

        if not self.current_question:
            print("⚠️ No current question to save")
            return

        # Add message to current session
        import datetime
        if not self.current_session["started_at"]:
            self.current_session["started_at"] = datetime.datetime.utcnow().isoformat()

        self.current_session["messages"].append({
            "question": self.current_question,
            "response": response_text,
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        print(f"✅ Message added to session ({len(self.current_session['messages'])} messages total)")

        # Clear the current question
        self.current_question = None

        # Auto-save session to Firestore after each message
        self._save_session_to_firestore()

    def start_new_conversation(self):
        """Start a new conversation session (clears current session)"""
        if self.current_session["messages"]:
            # Save current session before starting new one
            self._save_session_to_firestore()

            # Show confirmation
            msg_count = len(self.current_session["messages"])
            self.signals.log.emit(f"<span style='color: #10B981;'>✅ Saved conversation with {msg_count} messages</span>")

        # Reset session
        import datetime
        self.current_session = {
            "messages": [],
            "started_at": None,
            "last_document_id": None
        }

        # Clear response area
        self.response_area.clear_messages()

        # Clear conversation context
        self.conversation_context = None

        print("🆕 Started new conversation session")
        self.signals.log.emit("<span style='color: #60A5FA;'>🆕 New conversation started</span>")

    def _save_session_to_firestore(self):
        """Save or update the current conversation session to Firestore"""
        if not self.current_session["messages"]:
            return

        # Get user ID
        user_id = self.firebase_auth.get_user_id()
        if not user_id:
            return

        # Save in background thread
        def save_in_background():
            try:
                # Combine all messages into one conversation
                full_conversation = ""
                for i, msg in enumerate(self.current_session["messages"], 1):
                    full_conversation += f"**Q{i}:** {msg['question']}\n\n"
                    full_conversation += f"**A{i}:** {msg['response']}\n\n---\n\n"

                # Get first question as title
                first_question = self.current_session["messages"][0]["question"]

                # Update existing document or create new
                if self.current_session["last_document_id"]:
                    # Update existing conversation
                    result = self.chat_manager.update_chat(
                        document_id=self.current_session["last_document_id"],
                        message=first_question,
                        response=full_conversation,
                        metadata={
                            "email": self.firebase_auth.get_user_email(),
                            "display_name": self.firebase_auth.get_user_display_name(),
                            "message_count": len(self.current_session["messages"]),
                            "started_at": self.current_session["started_at"],
                            "is_session": True,
                            "last_updated": datetime.datetime.utcnow().isoformat()
                        }
                    )
                else:
                    # Create new conversation
                    result = self.chat_manager.save_chat(
                        user_id=user_id,
                        message=first_question,
                        response=full_conversation,
                        message_type="conversation",
                        metadata={
                            "email": self.firebase_auth.get_user_email(),
                            "display_name": self.firebase_auth.get_user_display_name(),
                            "message_count": len(self.current_session["messages"]),
                            "started_at": self.current_session["started_at"],
                            "is_session": True
                        },
                        conversation_context=self.conversation_context
                    )

                if result["success"]:
                    self.current_session["last_document_id"] = result["document_id"]
                    print(f"✅ Session saved to Firestore: {result['document_id']}")
                else:
                    print(f"❌ Failed to save session: {result['message']}")
            except Exception as e:
                print(f"❌ Error saving session to Firestore: {e}")
                import traceback
                traceback.print_exc()

        # Run in background thread
        threading.Thread(target=save_in_background, daemon=True).start()

    def retrieve_user_chats(self, limit: int = 10):
        """Retrieve and display user's chat history from Firestore"""
        # Check if we have all required components
        if not self.chat_manager or not self.chat_manager.is_available():
            self.signals.log.emit("<span style='color: #EF4444;'>⚠️ Chat manager not available</span>")
            return

        if not self.firebase_auth or not self.firebase_auth.is_authenticated():
            self.signals.log.emit("<span style='color: #EF4444;'>⚠️ Please sign in to view chat history</span>")
            return

        # Get user ID
        user_id = self.firebase_auth.get_user_id()
        if not user_id:
            self.signals.log.emit("<span style='color: #EF4444;'>⚠️ Could not get user ID</span>")
            return

        # Retrieve chats in background thread
        def retrieve_in_background():
            try:
                result = self.chat_manager.retrieve_chats(user_id=user_id, limit=limit)
                if result["success"]:
                    chats = result["chats"]
                    self.signals.log.emit(f"<span style='color: #10B981;'>✅ Retrieved {len(chats)} chats</span>")

                    # Display chats in response area
                    if chats:
                        chat_display = f"### Your Recent Chats ({len(chats)} total)\n\n"
                        for i, chat in enumerate(chats, 1):
                            created_at = chat.get("created_at", "Unknown time")
                            message = chat.get("message", "")
                            response = chat.get("response", "")
                            chat_display += f"**Chat {i}** - {created_at}\n\n"
                            chat_display += f"**Q:** {message}\n\n"
                            chat_display += f"**A:** {response[:200]}{'...' if len(response) > 200 else ''}\n\n"
                            chat_display += "---\n\n"

                        self.signals.response.emit(chat_display)
                    else:
                        self.signals.response.emit("No chat history found.")
                else:
                    self.signals.log.emit(f"<span style='color: #EF4444;'>❌ {result['message']}</span>")
            except Exception as e:
                self.signals.log.emit(f"<span style='color: #EF4444;'>❌ Error retrieving chats: {str(e)}</span>")
                import traceback
                traceback.print_exc()

        # Run in background thread
        threading.Thread(target=retrieve_in_background, daemon=True).start()

    def load_chat_history(self):
        """Load chat history into the history list widget"""
        if not self.chat_manager or not self.chat_manager.is_available():
            self.signals.log.emit("<span style='color: #EF4444;'>⚠️ Chat manager not available</span>")
            return

        if not self.firebase_auth or not self.firebase_auth.is_authenticated():
            self.signals.log.emit("<span style='color: #EF4444;'>⚠️ Please sign in to view chat history</span>")
            return

        user_id = self.firebase_auth.get_user_id()
        if not user_id:
            self.signals.log.emit("<span style='color: #EF4444;'>⚠️ Could not get user ID</span>")
            return

        # Clear current list
        self.history_list.clear()
        self.signals.log.emit("<span style='color: #60A5FA;'>🔄 Loading chat history...</span>")

        # Load chats in background
        def load_in_background():
            try:
                result = self.chat_manager.retrieve_chats(user_id=user_id, limit=50)
                if result["success"]:
                    chats = result["chats"]
                    # Send chats to UI thread for display
                    _from_companion_q.put(("CHAT_HISTORY_LOADED", chats))
                else:
                    self.signals.log.emit(f"<span style='color: #EF4444;'>❌ {result['message']}</span>")
            except Exception as e:
                self.signals.log.emit(f"<span style='color: #EF4444;'>❌ Error loading history: {str(e)}</span>")
                import traceback
                traceback.print_exc()

        threading.Thread(target=load_in_background, daemon=True).start()

    def display_chat_history(self, chats):
        """Display loaded chats in the history list"""
        self.history_list.clear()

        if not chats:
            item = QListWidgetItem("No chat history found")
            item.setData(Qt.ItemDataRole.UserRole, None)
            self.history_list.addItem(item)
            self.signals.log.emit("<span style='color: #9CA3AF;'>No chat history found</span>")
            return

        self.signals.log.emit(f"<span style='color: #10B981;'>✅ Loaded {len(chats)} chats</span>")

        for chat in chats:
            message = chat.get("message", "")
            response = chat.get("response", "")
            created_at = chat.get("created_at", "Unknown time")
            doc_id = chat.get("document_id", "")

            # Format timestamp (just date and time)
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                time_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                time_str = created_at[:16] if len(created_at) > 16 else created_at

            # Create list item with preview of both question and answer
            question_preview = message[:50] + "..." if len(message) > 50 else message
            response_preview = response[:50] + "..." if len(response) > 50 else response
            item_text = f"📝 {time_str}\nQ: {question_preview}\nA: {response_preview}"

            item = QListWidgetItem(item_text)
            # Store full chat data in item
            item.setData(Qt.ItemDataRole.UserRole, chat)
            self.history_list.addItem(item)

    def load_selected_chat(self):
        """Load the selected chat into the chat tab"""
        selected_items = self.history_list.selectedItems()
        if not selected_items:
            self.signals.log.emit("<span style='color: #F59E0B;'>⚠️ Please select a chat to load</span>")
            return

        chat_data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if not chat_data:
            return

        # Display the chat in the response area
        message = chat_data.get("message", "")
        response = chat_data.get("response", "")
        created_at = chat_data.get("created_at", "")

        # Format the chat display
        chat_display = f"### 📜 Previous Conversation\n\n"
        chat_display += f"**Date:** {created_at}\n\n"
        chat_display += f"**Your Question:**\n{message}\n\n"
        chat_display += f"**Response:**\n{response}\n\n"
        chat_display += "---\n\n"
        chat_display += "*You can now ask a follow-up question to continue this conversation.*"

        self.response_area.clear_messages()
        self.signals.response.emit(chat_display)

        # Switch to Chat tab
        self.tabs.setCurrentIndex(0)

        # Store conversation context for follow-up
        self.conversation_context = {
            "previous_message": message,
            "previous_response": response,
            "document_id": chat_data.get("document_id", "")
        }

        self.signals.log.emit("<span style='color: #10B981;'>✅ Chat loaded. Ask a follow-up question to continue.</span>")

    def on_history_item_double_clicked(self, item):
        """Handle double-click on history item"""
        self.load_selected_chat()

    def delete_selected_chat(self):
        """Delete the selected chat from Firestore"""
        selected_items = self.history_list.selectedItems()
        if not selected_items:
            self.signals.log.emit("<span style='color: #F59E0B;'>⚠️ Please select a chat to delete</span>")
            return

        chat_data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if not chat_data:
            return

        doc_id = chat_data.get("document_id", "")
        if not doc_id:
            self.signals.log.emit("<span style='color: #EF4444;'>❌ Cannot delete: missing document ID</span>")
            return

        # Confirm deletion
        message = chat_data.get("message", "")[:50]
        reply = QMessageBox.question(
            self,
            "Delete Chat",
            f"Are you sure you want to delete this chat?\n\n\"{message}...\"",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Delete in background
            def delete_in_background():
                try:
                    result = self.chat_manager.delete_chat(doc_id)
                    if result["success"]:
                        self.signals.log.emit("<span style='color: #10B981;'>✅ Chat deleted successfully</span>")
                        # Reload history
                        self.load_chat_history()
                    else:
                        self.signals.log.emit(f"<span style='color: #EF4444;'>❌ {result['message']}</span>")
                except Exception as e:
                    self.signals.log.emit(f"<span style='color: #EF4444;'>❌ Error deleting chat: {str(e)}</span>")

            threading.Thread(target=delete_in_background, daemon=True).start()

    def init_ui(self):
        self.setWindowTitle("Ghost")

        # Set app icon
        icon_path = resource_path("icons/logo-main.png")
        if os.path.exists(icon_path):
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))

        # Visual sizing - taller to maximize chat area
        self.setFixedSize(440, 700)

        # Main container widget with rounded corners
        container = QWidget()
        container.setObjectName("container")

        # Layouts
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QVBoxLayout()
        content.setContentsMargins(20, 20, 20, 20)
        content.setSpacing(16)

        # Title bar area (draggable) with modern header
        title_section = QVBoxLayout()
        title_section.setSpacing(10)

        title_h = QHBoxLayout()
        title_h.setSpacing(10)

        # Logo (10x bigger: 240x240)
        logo_label = QLabel()
        logo_path = resource_path("icons/logo-main.png")
        if os.path.exists(logo_path):
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(logo_path)
            scaled_pixmap = pixmap.scaled(35, 35, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            title_h.addWidget(logo_label)

        # Status indicator dot - REMOVED (was distracting)
        # self.status_dot = QLabel("●")
        # self.status_dot.setObjectName("statusDot")
        # self.status_dot.setStyleSheet("color: #6B7280; font-size: 16px;")
        # title_h.addWidget(self.status_dot)

        title_lbl = QLabel("Ghost - Update Test")
        title_lbl.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_h.addWidget(title_lbl)
        title_h.addStretch()

        # Status label with modern styling
        self.status_lbl = QLabel("Idle")
        self.status_lbl.setObjectName("statusLabel")
        status_font = QFont()
        status_font.setPointSize(9)
        self.status_lbl.setFont(status_font)
        title_h.addWidget(self.status_lbl)

        title_section.addLayout(title_h)

        # Separator line
        separator1 = QLabel()
        separator1.setFixedHeight(1)
        separator1.setStyleSheet("background: rgba(255, 255, 255, 0.08);")
        title_section.addWidget(separator1)

        content.addLayout(title_section)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setObjectName("modernTabs")
        content.addWidget(self.tabs)

        # === CHAT TAB ===
        chat_tab = QWidget()
        chat_layout = QVBoxLayout(chat_tab)
        chat_layout.setContentsMargins(0, 8, 0, 0)
        chat_layout.setSpacing(8)

        # Top buttons row
        btn_h = QHBoxLayout()
        btn_h.setSpacing(8)

        # New Conversation button
        self.new_conversation_btn = QPushButton("New Chat")
        self.new_conversation_btn.setObjectName("accentButton")
        self.new_conversation_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_conversation_btn.clicked.connect(self.start_new_conversation)
        self.new_conversation_btn.setFixedHeight(32)
        self.new_conversation_btn.setToolTip("Start a new conversation (saves current one)")
        btn_h.addWidget(self.new_conversation_btn, 1)

        # Recording status label
        self.recording_status_label = QLabel("🔴 Recording Active")
        self.recording_status_label.setStyleSheet("""
            QLabel {
                color: #10B981;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 12px;
                background-color: rgba(16, 185, 129, 0.1);
                border-radius: 6px;
            }
        """)
        self.recording_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_h.addWidget(self.recording_status_label, 2)

        self.hide_btn = QPushButton("Hide")
        self.hide_btn.setObjectName("secondaryButton")
        self.hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_btn.clicked.connect(self.toggle_visibility)
        self.hide_btn.setFixedHeight(32)
        btn_h.addWidget(self.hide_btn, 1)
        chat_layout.addLayout(btn_h)

        # Guidance mode toggle
        guidance_h = QHBoxLayout()
        guidance_h.setSpacing(12)

        self.guidance_mode_checkbox = QCheckBox("Guidance Mode")
        self.guidance_mode_checkbox.setObjectName("modernCheckbox")
        self.guidance_mode_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.guidance_mode_checkbox.setToolTip("Enable real-time screen capture and instant AI guidance")
        guidance_h.addWidget(self.guidance_mode_checkbox)

        guidance_label = QLabel("(Live screen capture + instant responses)")
        guidance_label.setObjectName("subtleLabel")
        guidance_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        guidance_h.addWidget(guidance_label)

        guidance_h.addStretch()
        chat_layout.addLayout(guidance_h)

        # Response display - maximize this area, no border
        self.response_area = MarkdownTextEdit()
        self.response_area.setObjectName("modernTextArea")
        self.response_area.setReadOnly(True)
        chat_layout.addWidget(self.response_area, 1)  # Stretch factor 1 to maximize

        # Ask question section at bottom - compact
        ask_input_h = QHBoxLayout()
        ask_input_h.setSpacing(8)

        self.ask_edit = QLineEdit()
        self.ask_edit.setObjectName("modernInput")
        self.ask_edit.setPlaceholderText("Ask Anything")
        self.ask_edit.returnPressed.connect(self.on_ask)
        self.ask_edit.setFixedHeight(36)
        ask_input_h.addWidget(self.ask_edit)

        self.ask_btn = QPushButton("Send")
        self.ask_btn.setObjectName("accentButton")
        self.ask_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ask_btn.clicked.connect(self.on_ask)
        self.ask_btn.setFixedHeight(36)
        self.ask_btn.setFixedWidth(70)
        ask_input_h.addWidget(self.ask_btn)

        chat_layout.addLayout(ask_input_h)

        # Add chat tab
        self.tabs.addTab(chat_tab, "Chat")

        # === HISTORY TAB ===
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        history_layout.setContentsMargins(0, 16, 0, 0)
        history_layout.setSpacing(12)

        # Header with refresh button
        history_header_h = QHBoxLayout()
        history_header_h.setSpacing(10)

        history_lbl = QLabel("CHAT HISTORY")
        history_lbl.setObjectName("sectionLabel")
        history_header_h.addWidget(history_lbl)

        history_header_h.addStretch()

        self.refresh_history_btn = QPushButton("🔄 Refresh")
        self.refresh_history_btn.setObjectName("secondaryButton")
        self.refresh_history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_history_btn.clicked.connect(self.load_chat_history)
        self.refresh_history_btn.setFixedHeight(32)
        self.refresh_history_btn.setFixedWidth(100)
        history_header_h.addWidget(self.refresh_history_btn)

        history_layout.addLayout(history_header_h)

        # Info label
        history_info_lbl = QLabel("View and continue your previous conversations")
        history_info_lbl.setObjectName("subtleLabel")
        history_info_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px; margin-bottom: 8px;")
        history_layout.addWidget(history_info_lbl)

        # Chat history list
        self.history_list = QListWidget()
        self.history_list.setObjectName("modernList")
        self.history_list.itemDoubleClicked.connect(self.on_history_item_double_clicked)
        self.history_list.setStyleSheet("""
            QListWidget#modernList {
                background-color: transparent;
                border: none;
                padding: 0px;
                color: #E5E7EB;
                font-size: 12px;
            }
            QListWidget#modernList::item {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 12px;
                margin-bottom: 8px;
            }
            QListWidget#modernList::item:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-color: rgba(96, 165, 250, 0.5);
            }
            QListWidget#modernList::item:selected {
                background-color: rgba(96, 165, 250, 0.2);
                border-color: #60A5FA;
            }
        """)
        history_layout.addWidget(self.history_list)

        # Action buttons
        history_actions_h = QHBoxLayout()
        history_actions_h.setSpacing(8)

        self.load_chat_btn = QPushButton("📖 Load Chat")
        self.load_chat_btn.setObjectName("accentButton")
        self.load_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_chat_btn.clicked.connect(self.load_selected_chat)
        self.load_chat_btn.setFixedHeight(36)
        history_actions_h.addWidget(self.load_chat_btn)

        self.delete_chat_btn = QPushButton("🗑️ Delete")
        self.delete_chat_btn.setObjectName("secondaryButton")
        self.delete_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_chat_btn.clicked.connect(self.delete_selected_chat)
        self.delete_chat_btn.setFixedHeight(36)
        history_actions_h.addWidget(self.delete_chat_btn)

        history_layout.addLayout(history_actions_h)

        # Add history tab
        self.tabs.addTab(history_tab, "History")

        # === SETTINGS TAB ===
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.setContentsMargins(0, 16, 0, 0)
        settings_layout.setSpacing(16)

        # Config section
        cfg_lbl = QLabel("CONFIGURATION")
        cfg_lbl.setObjectName("sectionLabel")
        settings_layout.addWidget(cfg_lbl)

        # User ID (for mem0 per-user memory separation) - displayed as plain text
        user_id_h = QHBoxLayout()
        user_id_h.setSpacing(10)

        user_id_label = QLabel("User ID:")
        user_id_label.setObjectName("fieldLabel")
        user_id_h.addWidget(user_id_label)

        self.user_id_display = QLabel(self.config.get("user_id", "default_user"))
        self.user_id_display.setObjectName("fieldValue")
        self.user_id_display.setStyleSheet("color: #D4D4D8; font-size: 12px; font-weight: 500;")
        user_id_h.addWidget(self.user_id_display)
        user_id_h.addStretch()
        settings_layout.addLayout(user_id_h)

        # Info label about automatic settings
        info_label = QLabel("Recording and analysis settings are automatically optimized for best performance and cost efficiency.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #9CA3AF; font-size: 11px; padding: 8px; background-color: rgba(255,255,255,0.03); border-radius: 6px;")
        settings_layout.addWidget(info_label)

        # Watch directories with modern list
        watch_header = QHBoxLayout()
        watch_header.setSpacing(0)
        watch_lbl = QLabel("WATCHED DIRECTORIES")
        watch_lbl.setObjectName("sectionLabel")
        watch_header.addWidget(watch_lbl)
        watch_header.addStretch()
        settings_layout.addLayout(watch_header)

        self.watch_list = QListWidget()
        self.watch_list.setObjectName("modernList")
        self.watch_list.setFixedHeight(70)
        for d in self.config.get("watch_dirs", []):
            self.watch_list.addItem(QListWidgetItem(d))
        settings_layout.addWidget(self.watch_list)

        watch_btn_h = QHBoxLayout()
        watch_btn_h.setSpacing(10)

        add_dir_btn = QPushButton("+ Add Directory")
        add_dir_btn.setObjectName("secondaryButton")
        add_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_dir_btn.clicked.connect(self.on_add_dir)
        add_dir_btn.setFixedHeight(36)
        watch_btn_h.addWidget(add_dir_btn)

        remove_dir_btn = QPushButton("Remove")
        remove_dir_btn.setObjectName("textButton")
        remove_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_dir_btn.clicked.connect(self.on_remove_dir)
        remove_dir_btn.setFixedHeight(36)
        watch_btn_h.addWidget(remove_dir_btn)
        settings_layout.addLayout(watch_btn_h)

        # Startup behavior section
        startup_lbl = QLabel("STARTUP BEHAVIOR")
        startup_lbl.setObjectName("sectionLabel")
        settings_layout.addWidget(startup_lbl)

        # Start on boot checkbox
        from onboarding import OnboardingDialog
        self.start_on_boot_checkbox = QCheckBox("Start Ghost when Windows starts")
        self.start_on_boot_checkbox.setObjectName("modernCheckBox")
        self.start_on_boot_checkbox.setStyleSheet("""
            QCheckBox {
                color: #D4D4D8;
                font-size: 12px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid #52525B;
                border-radius: 4px;
                background-color: #18181B;
            }
            QCheckBox::indicator:checked {
                background-color: #4285f4;
                border-color: #4285f4;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEzLjUgNEw2IDExLjVMMi41IDgiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPgo=);
            }
            QCheckBox::indicator:hover {
                border-color: #71717A;
            }
        """)
        self.start_on_boot_checkbox.setChecked(OnboardingDialog.is_start_on_boot_enabled())
        self.start_on_boot_checkbox.stateChanged.connect(self.on_start_on_boot_changed)
        settings_layout.addWidget(self.start_on_boot_checkbox)

        settings_layout.addStretch()

        # Add settings tab
        self.tabs.addTab(settings_tab, "Settings")

        # === ACCOUNT TAB ===
        account_tab = QWidget()
        account_layout = QVBoxLayout(account_tab)
        account_layout.setContentsMargins(0, 16, 0, 0)
        account_layout.setSpacing(16)

        # Auth status indicator
        self.auth_status_lbl = QLabel("Not authenticated")
        self.auth_status_lbl.setObjectName("sectionLabel")
        account_layout.addWidget(self.auth_status_lbl)

        # Info text
        info_lbl = QLabel("Sign in with your Google account to access personalized features")
        info_lbl.setObjectName("fieldLabel")
        info_lbl.setStyleSheet("color: #A1A1AA; font-size: 11px; margin-top: 10px;")
        info_lbl.setWordWrap(True)
        account_layout.addWidget(info_lbl)

        # Google Sign-In button (larger, prominent)
        self.google_signin_btn = QPushButton("🔐 Sign in with Google")
        self.google_signin_btn.setObjectName("googleSignInButton")
        self.google_signin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.google_signin_btn.clicked.connect(self.on_google_signin)
        self.google_signin_btn.setFixedHeight(50)
        self.google_signin_btn.setStyleSheet("""
            #googleSignInButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FFFFFF,
                    stop:1 #F5F5F5
                );
                color: #3C4043;
                border: 1px solid #DADCE0;
                border-radius: 12px;
                font-weight: 600;
                font-size: 14px;
                letter-spacing: -0.2px;
            }
            #googleSignInButton:hover {
                background: #F8F9FA;
                border: 1px solid #C0C0C0;
            }
            #googleSignInButton:pressed {
                background: #E8EAED;
            }
        """)
        account_layout.addWidget(self.google_signin_btn)

        # Sign out button (no anonymous login)
        self.signout_btn = QPushButton("Sign Out")
        self.signout_btn.setObjectName("secondaryButton")
        self.signout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.signout_btn.clicked.connect(self.on_signout)
        self.signout_btn.setFixedHeight(38)
        self.signout_btn.setEnabled(False)
        account_layout.addWidget(self.signout_btn)

        # User info display
        user_info_lbl = QLabel("USER INFO")
        user_info_lbl.setObjectName("sectionLabel")
        account_layout.addWidget(user_info_lbl)

        self.user_info_area = QTextEdit()
        self.user_info_area.setObjectName("modernTextArea")
        self.user_info_area.setReadOnly(True)
        self.user_info_area.setFixedHeight(120)
        self.user_info_area.setPlaceholderText("User information will appear here after authentication...")
        account_layout.addWidget(self.user_info_area)

        # Firebase status
        if FIREBASE_AVAILABLE:
            firebase_status = "Firebase Auth: Ready"
            if not self.firebase_auth:
                firebase_status = "Firebase Auth: Config not found (create firebase_config.json)"
        else:
            firebase_status = "Firebase Auth: Not installed (pip install pyrebase4)"

        status_lbl = QLabel(firebase_status)
        status_lbl.setObjectName("fieldLabel")
        status_lbl.setStyleSheet("color: #71717A; font-size: 10px; margin-top: 10px;")
        status_lbl.setWordWrap(True)
        account_layout.addWidget(status_lbl)

        account_layout.addStretch()

        # Add account tab
        self.tabs.addTab(account_tab, "Account")

        # === CONNECTED APPS TAB ===
        apps_tab = QWidget()
        apps_layout = QVBoxLayout(apps_tab)
        apps_layout.setContentsMargins(0, 16, 0, 0)
        apps_layout.setSpacing(16)

        # GitHub Authentication Section
        github_header = QLabel("GITHUB INTEGRATION")
        github_header.setObjectName("sectionLabel")
        apps_layout.addWidget(github_header)

        # GitHub info text
        github_info_lbl = QLabel("Sign in with GitHub to access repository tools and generate content from commits")
        github_info_lbl.setObjectName("fieldLabel")
        github_info_lbl.setStyleSheet("color: #A1A1AA; font-size: 11px; margin-top: 10px;")
        github_info_lbl.setWordWrap(True)
        apps_layout.addWidget(github_info_lbl)

        # GitHub Sign-In button
        self.github_signin_btn = QPushButton("🔗 Sign in with GitHub")
        self.github_signin_btn.setObjectName("githubSignInButton")
        self.github_signin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.github_signin_btn.clicked.connect(self.on_github_signin)
        self.github_signin_btn.setFixedHeight(50)
        self.github_signin_btn.setStyleSheet("""
            #githubSignInButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #24292E,
                    stop:1 #1B1F23
                );
                color: #FFFFFF;
                border: 1px solid #30363D;
                border-radius: 12px;
                font-weight: 600;
                font-size: 14px;
                letter-spacing: -0.2px;
            }
            #githubSignInButton:hover {
                background: #30363D;
                border: 1px solid #484F58;
            }
            #githubSignInButton:pressed {
                background: #1B1F23;
            }
        """)
        apps_layout.addWidget(self.github_signin_btn)

        # GitHub user info
        self.github_user_lbl = QLabel("Not connected")
        self.github_user_lbl.setObjectName("fieldLabel")
        self.github_user_lbl.setStyleSheet("color: #71717A; font-size: 11px; margin-top: 8px;")
        apps_layout.addWidget(self.github_user_lbl)

        # GitHub status
        if GITHUB_AVAILABLE:
            github_status = "GitHub Integration: Ready"
        else:
            github_status = "GitHub Integration: Not installed (pip install PyGithub)"

        github_status_lbl = QLabel(github_status)
        github_status_lbl.setObjectName("fieldLabel")
        github_status_lbl.setStyleSheet("color: #71717A; font-size: 10px; margin-top: 10px;")
        github_status_lbl.setWordWrap(True)
        apps_layout.addWidget(github_status_lbl)

        apps_layout.addStretch()

        # Add connected apps tab
        self.tabs.addTab(apps_tab, "Connected Apps")

        # === MEMORIES TAB ===
        memories_tab = QWidget()
        memories_layout = QVBoxLayout(memories_tab)
        memories_layout.setContentsMargins(0, 16, 0, 0)
        memories_layout.setSpacing(12)

        # Top section with search and buttons
        top_section = QHBoxLayout()
        top_section.setSpacing(8)

        self.memory_search = QLineEdit()
        self.memory_search.setObjectName("modernInput")
        self.memory_search.setPlaceholderText("Search memories...")
        self.memory_search.textChanged.connect(self.on_memory_search)
        self.memory_search.setFixedHeight(32)
        top_section.addWidget(self.memory_search, 1)

        search_btn = QPushButton("Search")
        search_btn.setObjectName("accentButton")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.clicked.connect(self.on_memory_search_btn)
        search_btn.setFixedHeight(32)
        search_btn.setFixedWidth(70)
        top_section.addWidget(search_btn)

        refresh_btn = QPushButton("↻")
        refresh_btn.setObjectName("iconButton")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.on_refresh_memories)
        refresh_btn.setFixedSize(32, 32)
        refresh_btn.setToolTip("Refresh memories")
        top_section.addWidget(refresh_btn)

        memories_layout.addLayout(top_section)

        # Scroll area for memory cards
        scroll_area = QScrollArea()
        scroll_area.setObjectName("memoryScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Container widget for memory cards
        self.memories_container = QWidget()
        self.memories_container.setObjectName("memoriesContainer")
        self.memories_cards_layout = QVBoxLayout(self.memories_container)
        self.memories_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.memories_cards_layout.setSpacing(8)
        self.memories_cards_layout.addStretch()

        scroll_area.setWidget(self.memories_container)
        memories_layout.addWidget(scroll_area, 1)

        # Status label for memory operations
        self.memory_status_lbl = QLabel("")
        self.memory_status_lbl.setObjectName("fieldLabel")
        self.memory_status_lbl.setStyleSheet("color: #71717A; font-size: 9px; margin-top: 4px;")
        self.memory_status_lbl.setWordWrap(True)
        memories_layout.addWidget(self.memory_status_lbl)

        # Store selected memory ID for deletion
        self.selected_memory_id = None

        # Add memories tab
        self.tabs.addTab(memories_tab, "Memories")

        container.setLayout(content)
        root.addWidget(container)
        self.setLayout(root)

        # Apply modern glassmorphism style
        self.apply_modern_style()

        # Add subtle drop shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(50)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 12)
        container.setGraphicsEffect(shadow)

        # Restore authentication state if available
        if hasattr(self, '_pending_auth_restore') and self._pending_auth_restore:
            # Use QTimer.singleShot to defer the UI update until after the event loop starts
            QTimer.singleShot(100, lambda: self.signals.auth_update.emit(self._pending_auth_restore))
            QTimer.singleShot(100, lambda: self.signals.log.emit(f"<span style='color: #10B981;'>✅ Restored session: {self._pending_auth_restore.get('email', 'Anonymous')}</span>"))

        # Restore GitHub authentication state if available
        if hasattr(self, '_pending_github_restore') and self._pending_github_restore:
            username = self._pending_github_restore.get('login', 'Unknown')
            # Use QTimer.singleShot to defer the UI update until after the event loop starts
            QTimer.singleShot(100, lambda u=username: self.update_github_ui_state(u))
            QTimer.singleShot(100, lambda u=username: self.signals.log.emit(f"<span style='color: #10B981;'>✅ GitHub: Restored session for {u}</span>"))

        # Update chat enabled state based on authentication
        self.update_chat_enabled_state()

    def apply_modern_style(self):
        self.setStyleSheet("""
            /* Main container with glassmorphism effect - Translucent gray */
            #container {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(24, 24, 27, 0.92),
                    stop:1 rgba(18, 18, 21, 0.95)
                );
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }

            /* Typography */
            #titleLabel {
                color: #FAFAFA;
                font-weight: 600;
                letter-spacing: -0.3px;
            }

            #statusLabel {
                color: #A1A1AA;
                background: rgba(255, 255, 255, 0.04);
                padding: 6px 14px;
                border-radius: 14px;
                font-weight: 500;
            }

            #sectionLabel {
                color: #A1A1AA;
                font-size: 9px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 1.3px;
                margin: 0;
                padding: 20px 0 0 0;
            }

            #fieldLabel {
                color: #D4D4D8;
                font-size: 12px;
                font-weight: 500;
            }
            
            /* Primary button - gray gradient */
            #primaryButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563EB,
                    stop:1 #1D4ED8
                );
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                letter-spacing: -0.2px;
            }

            #primaryButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1D4ED8,
                    stop:1 #1E40AF
                );
            }

            #primaryButton:pressed {
                background: #1E3A8A;
            }

            /* Secondary button */
            #secondaryButton {
                background: rgba(255, 255, 255, 0.06);
                color: #FAFAFA;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                font-weight: 500;
                font-size: 11px;
                letter-spacing: -0.2px;
            }

            #secondaryButton:hover {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.14);
            }

            #secondaryButton:pressed {
                background: rgba(255, 255, 255, 0.04);
            }

            /* Accent button */
            #accentButton {
                background: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 12px;
                letter-spacing: -0.2px;
            }

            #accentButton:hover {
                background: #059669;
            }

            #accentButton:pressed {
                background: #047857;
            }

            /* Text button */
            #textButton {
                background: transparent;
                color: #71717A;
                border: none;
                font-size: 11px;
                font-weight: 600;
                padding: 0 10px;
            }

            #textButton:hover {
                color: #D4D4D8;
                background: rgba(255, 255, 255, 0.06);
                border-radius: 8px;
            }
            
            /* Modern inputs */
            #modernInput {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #FAFAFA;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 400;
            }

            #modernInput:focus {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(59, 130, 246, 0.4);
                outline: none;
            }

            #modernInput::placeholder {
                color: #52525B;
                font-weight: 400;
            }

            /* Text areas - transparent background, no border */
            #modernTextArea {
                background: transparent;
                border: none;
                border-radius: 0px;
                color: #E4E4E7;
                padding: 14px;
                font-size: 12px;
                font-family: 'SF Mono', 'Consolas', 'Monaco', monospace;
                line-height: 1.6;
            }
            
            /* Spin box */
            #modernSpinBox {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #FAFAFA;
                padding: 0 12px;
                font-size: 13px;
                font-weight: 500;
            }

            #modernSpinBox::up-button, #modernSpinBox::down-button {
                background: rgba(255, 255, 255, 0.06);
                border: none;
                border-radius: 6px;
                width: 24px;
            }

            #modernSpinBox::up-button:hover, #modernSpinBox::down-button:hover {
                background: rgba(255, 255, 255, 0.12);
            }

            /* Combo box */
            #modernComboBox {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #FAFAFA;
                padding: 0 12px;
                font-size: 13px;
                font-weight: 500;
            }

            #modernComboBox:hover {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
            }

            #modernComboBox::drop-down {
                border: none;
                background: transparent;
                width: 30px;
            }

            #modernComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #A1A1AA;
                margin-right: 8px;
            }

            #modernComboBox QAbstractItemView {
                background: #27272A;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                color: #FAFAFA;
                selection-background-color: rgba(59, 130, 246, 0.25);
                selection-color: #FAFAFA;
                padding: 4px;
            }

            #modernComboBox QAbstractItemView::item {
                padding: 8px 12px;
                border-radius: 6px;
                min-height: 30px;
            }

            #modernComboBox QAbstractItemView::item:hover {
                background: rgba(255, 255, 255, 0.08);
            }

            #modernComboBox QAbstractItemView::item:selected {
                background: rgba(59, 130, 246, 0.25);
            }

            /* List widget */
            #modernList {
                background: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                color: #D4D4D8;
                padding: 6px;
                font-size: 11px;
            }

            #modernList::item {
                padding: 8px 12px;
                border-radius: 6px;
                margin: 3px;
            }

            #modernList::item:selected {
                background: rgba(59, 130, 246, 0.25);
                color: #FAFAFA;
                border: 1px solid rgba(59, 130, 246, 0.3);
            }

            #modernList::item:hover {
                background: rgba(255, 255, 255, 0.04);
            }

            /* Scrollbars */
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                border-radius: 3px;
                margin: 2px;
            }

            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 3px;
                min-height: 30px;
            }

            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.25);
            }

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            /* Tab Widget - full width tabs */
            QTabWidget::pane {
                border: none;
                background: transparent;
                margin-top: 0px;
            }

            QTabBar {
                qproperty-expanding: true;
            }

            QTabBar::tab {
                background: rgba(255, 255, 255, 0.04);
                color: #71717A;
                border: none;
                border-radius: 0px;
                padding: 10px 20px;
                margin: 0px;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.3px;
                min-width: 0px;
            }

            QTabBar::tab:selected {
                background: rgba(255, 255, 255, 0.08);
                color: #FAFAFA;
            }

            QTabBar::tab:hover:!selected {
                background: rgba(255, 255, 255, 0.06);
                color: #A1A1AA;
            }

            /* Memory Cards */
            #memoryScrollArea {
                background: transparent;
                border: none;
            }

            #memoriesContainer {
                background: transparent;
            }

            #memoryCard {
                background: rgba(255, 255, 255, 0.03);
                border: none;
                border-radius: 8px;
                margin: 0px;
            }

            #memoryCard:hover {
                background: rgba(255, 255, 255, 0.05);
            }

            #memoryDeleteBtn {
                background: transparent;
                color: #71717A;
                border: none;
                border-radius: 10px;
                font-size: 18px;
                font-weight: 300;
            }

            #memoryDeleteBtn:hover {
                background: rgba(239, 68, 68, 0.15);
                color: #EF4444;
            }

            #memoryDeleteBtn:pressed {
                background: rgba(239, 68, 68, 0.25);
            }

            /* Icon Button */
            #iconButton {
                background: rgba(255, 255, 255, 0.04);
                color: #D4D4D8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                font-size: 16px;
                font-weight: 400;
            }

            #iconButton:hover {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.12);
            }

            #iconButton:pressed {
                background: rgba(255, 255, 255, 0.03);
            }
        """)

    def on_add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select directory to watch")
        if d:
            self.watch_list.addItem(QListWidgetItem(d))

    def on_remove_dir(self):
        for item in list(self.watch_list.selectedItems()):
            self.watch_list.takeItem(self.watch_list.row(item))

    def on_start_on_boot_changed(self, state):
        """Handle start on boot checkbox state change"""
        from onboarding import OnboardingDialog
        if state == Qt.CheckState.Checked.value:
            OnboardingDialog.enable_start_on_boot(self)
        else:
            OnboardingDialog.disable_start_on_boot()

    def save_config(self):
        conf = self._gather_config_from_ui()
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(conf, f, indent=2)
            self.signals.log.emit(f"Config saved to {CONFIG_PATH}")
            self.signals.config_saved.emit()
        except Exception as e:
            self.signals.log.emit(f"Failed to save config: {e}")

    def on_config_saved(self):
        # Push updated config to companion thread
        conf = self._gather_config_from_ui()
        _to_companion_q.put(("UPDATE_CONFIG", conf))
        self.signals.log.emit("Updated companion config (queued).")

    def _gather_config_from_ui(self):
        watch_dirs = [self.watch_list.item(i).text() for i in range(self.watch_list.count())]
        return {
            "api_key": "",  # API key is hardcoded, not editable
            "user_id": self.user_id_display.text().strip() or "default_user",
            "interval": 40,  # Fixed optimal value for backward compatibility
            "analysis_interval": 40,  # Fixed optimal value
            "fps": 1,  # Fixed optimal value
            "watch_dirs": watch_dirs,
            "always_recent": self.config.get("always_recent", 3),
            "qa_model": "gemini",  # Fixed to Gemini
            "onboarding_completed": self.config.get("onboarding_completed", False)
        }

    def auto_start_recording(self):
        """Auto-start recording when app is active and authenticated"""
        if not self._is_recording:
            _to_companion_q.put(("START", None))
            self.signals.log.emit("🔴 Auto-started recording...")
            self._is_recording = True
            self.recording_status_label.setText("🔴 Recording Active")
            self.recording_status_label.setStyleSheet("""
                QLabel {
                    color: #10B981;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 8px 12px;
                    background-color: rgba(16, 185, 129, 0.1);
                    border-radius: 6px;
                }
            """)

    def update_chat_enabled_state(self):
        """Enable or disable chat based on authentication status"""
        is_authenticated = bool(self.firebase_auth and self.firebase_auth.is_authenticated())

        # Enable/disable chat input and button
        self.ask_edit.setEnabled(is_authenticated)
        self.ask_btn.setEnabled(is_authenticated)

        # Update placeholder text
        if not is_authenticated:
            self.ask_edit.setPlaceholderText("Sign in to use chat")
            self.response_area.setPlaceholderText("Please sign in to your Google account to use chat features")
            self.recording_status_label.setText("⚠️ Not Recording - Sign in required")
            self.recording_status_label.setStyleSheet("""
                QLabel {
                    color: #F59E0B;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 8px 12px;
                    background-color: rgba(245, 158, 11, 0.1);
                    border-radius: 6px;
                }
            """)
        else:
            self.ask_edit.setPlaceholderText("Ask Anything")
            self.response_area.setPlaceholderText("")
            # Auto-start recording when authenticated
            if not self._is_recording:
                self.auto_start_recording()

    def on_ask(self):
        # Check authentication before allowing chat
        if not (self.firebase_auth and self.firebase_auth.is_authenticated()):
            return

        q = self.ask_edit.text().strip()
        if not q:
            return

        # If there's conversation context, include it in the question
        enhanced_question = q
        if self.conversation_context:
            context_info = (
                f"\n\n[Context from previous conversation]\n"
                f"Previous question: {self.conversation_context['previous_message']}\n"
                f"Previous response: {self.conversation_context['previous_response'][:200]}...\n"
                f"[End of context]\n\n"
                f"Follow-up question: {q}"
            )
            enhanced_question = context_info

        # Store the original question for later saving with the response
        self.current_question = q

        # Display the user's question in the chat area
        import time
        ts = time.strftime("%H:%M:%S")
        question_html = (
            f"<div style='margin: 16px 0;'>"
            f"<div style='color: #9CA3AF; font-size: 10px; font-weight: 600; text-transform: uppercase; "
            f"letter-spacing: 1px; margin-bottom: 8px;'>YOU [{ts}]</div>"
            f"<div style='color: #E5E7EB; font-size: 13px; line-height: 1.6;'>{q}</div>"
            f"</div>"
        )
        self.response_area.append(question_html)

        # Auto-scroll to show the question
        cursor = self.response_area.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.response_area.setTextCursor(cursor)

        # Include guidance mode status with the question
        guidance_mode = self.guidance_mode_checkbox.isChecked()
        _to_companion_q.put(("ASK", {"question": enhanced_question, "guidance_mode": guidance_mode}))
        # optionally clear input
        self.ask_edit.clear()

        # Clear conversation context after sending follow-up
        # (so next question is fresh unless user loads another chat)
        if self.conversation_context:
            self.signals.log.emit("<span style='color: #60A5FA;'>💬 Continuing previous conversation...</span>")
            self.conversation_context = None

    def _check_for_updates_on_startup(self):
        """Check for updates in background on app startup"""
        def on_update_check_complete(update_info):
            # This will be called from background thread, so emit signal to update UI
            if update_info and update_info.get('available'):
                # Show update notification in UI thread via queue
                _from_companion_q.put(("UPDATE_AVAILABLE", update_info))

        # Check in background thread
        check_for_updates_background(callback=on_update_check_complete)

    def _show_update_notification(self, update_info):
        """Show update notification dialog with download option"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QProgressBar
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        import webbrowser

        dialog = QDialog(self)
        dialog.setWindowTitle("Update Available")
        dialog.setFixedWidth(500)
        dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1F2937,
                    stop:1 #111827
                );
                border-radius: 12px;
            }
            QLabel {
                color: #F3F4F6;
                padding: 8px;
            }
            QPushButton {
                background: #10B981;
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #059669;
            }
            QPushButton:pressed {
                background: #047857;
            }
            QProgressBar {
                border: 2px solid #374151;
                border-radius: 5px;
                text-align: center;
                background: #1F2937;
            }
            QProgressBar::chunk {
                background-color: #10B981;
                border-radius: 3px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Title
        title = QLabel("✨ Update Available!")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Version info
        version_text = f"Version {update_info['version']} is now available\n(You're on version {update_info['current_version']})"
        version_label = QLabel(version_text)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        layout.addWidget(version_label)

        # Changelog
        changelog_label = QLabel("What's New:")
        changelog_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(changelog_label)

        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        changelog_text.setMaximumHeight(150)
        changelog_text.setPlainText(update_info.get('changelog', 'No changelog available'))
        changelog_text.setStyleSheet("""
            QTextEdit {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 10px;
                color: #D1D5DB;
                font-size: 12px;
            }
        """)
        layout.addWidget(changelog_text)

        # Progress bar (hidden initially)
        self.update_progress_bar = QProgressBar()
        self.update_progress_bar.setTextVisible(True)
        self.update_progress_bar.setVisible(False)
        layout.addWidget(self.update_progress_bar)

        # Status label
        self.update_status_label = QLabel("")
        self.update_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_status_label.setStyleSheet("color: #60A5FA; font-size: 12px;")
        self.update_status_label.setVisible(False)
        layout.addWidget(self.update_status_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        download_btn = QPushButton("🚀 Download & Install")
        download_btn.clicked.connect(lambda: self._download_and_install_update(update_info, dialog))

        visit_btn = QPushButton("🌐 View on GitHub")
        visit_btn.setStyleSheet("""
            QPushButton {
                background: #3B82F6;
            }
            QPushButton:hover {
                background: #2563EB;
            }
        """)
        visit_btn.clicked.connect(lambda: webbrowser.open(update_info.get('release_url', '')))

        later_btn = QPushButton("Later")
        later_btn.setStyleSheet("""
            QPushButton {
                background: #374151;
            }
            QPushButton:hover {
                background: #4B5563;
            }
        """)
        later_btn.clicked.connect(dialog.accept)

        button_layout.addWidget(download_btn)
        button_layout.addWidget(visit_btn)
        button_layout.addWidget(later_btn)

        layout.addLayout(button_layout)

        dialog.setLayout(layout)
        dialog.exec()  # Modal dialog

    def _download_and_install_update(self, update_info, dialog):
        """Download and install update"""
        try:
            # Disable buttons
            for btn in dialog.findChildren(QPushButton):
                btn.setEnabled(False)

            # Show progress
            self.update_progress_bar.setVisible(True)
            self.update_status_label.setVisible(True)
            self.update_status_label.setText("Downloading update...")

            def progress_callback(stage, data):
                if stage == 'download_progress':
                    percent = data.get('percent', 0)
                    self.update_progress_bar.setValue(int(percent))
                    self.update_status_label.setText(f"Downloading... {int(percent)}%")
                elif stage == 'installing':
                    self.update_progress_bar.setValue(100)
                    self.update_status_label.setText("Installing update...")
                elif stage == 'complete':
                    self.update_status_label.setText("✓ Update installed! Restarting...")
                    QTimer.singleShot(2000, lambda: sys.exit(0))  # Exit app to allow update
                elif stage == 'error':
                    self.update_status_label.setText(f"❌ {data.get('message', 'Update failed')}")
                    self.update_status_label.setStyleSheet("color: #EF4444;")

            # Run update in background thread
            def run_update():
                checker = UpdateChecker()
                checker.auto_update(progress_callback=lambda s, d: _from_companion_q.put(("UPDATE_PROGRESS", (s, d))))

            threading.Thread(target=run_update, daemon=True).start()

        except Exception as e:
            self.signals.log.emit(f"<span style='color: #EF4444;'>Update failed: {str(e)}</span>")

    def _show_github_user_code_dialog(self, user_code, verification_url):
        """Show a dialog with the GitHub user code for authentication"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        import webbrowser

        dialog = QDialog(self)
        dialog.setWindowTitle("GitHub Authentication")
        dialog.setFixedWidth(450)
        dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1F2937,
                    stop:1 #111827
                );
                border-radius: 12px;
            }
            QLabel {
                color: #F3F4F6;
                padding: 8px;
            }
            QPushButton {
                background: #3B82F6;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2563EB;
            }
            QPushButton:pressed {
                background: #1D4ED8;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Title
        title = QLabel("🔐 GitHub Authentication")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Instructions
        instructions = QLabel("Please enter this code in your browser to authorize GitHub access:")
        instructions.setWordWrap(True)
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(instructions)

        # User code (large and centered)
        code_label = QLabel(user_code)
        code_font = QFont("Courier New")
        code_font.setPointSize(24)
        code_font.setBold(True)
        code_label.setFont(code_font)
        code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_label.setStyleSheet("""
            background: rgba(59, 130, 246, 0.2);
            border: 2px solid #3B82F6;
            border-radius: 8px;
            padding: 20px;
            color: #60A5FA;
            letter-spacing: 4px;
        """)
        layout.addWidget(code_label)

        # URL info
        url_label = QLabel(f"Browser opened to: {verification_url}")
        url_label.setWordWrap(True)
        url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_label.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        layout.addWidget(url_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        copy_btn = QPushButton("📋 Copy Code")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(user_code, dialog))

        open_browser_btn = QPushButton("🌐 Open Browser")
        open_browser_btn.clicked.connect(lambda: webbrowser.open(verification_url))

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background: #374151;
            }
            QPushButton:hover {
                background: #4B5563;
            }
        """)
        close_btn.clicked.connect(dialog.accept)

        button_layout.addWidget(copy_btn)
        button_layout.addWidget(open_browser_btn)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        dialog.setLayout(layout)
        dialog.show()  # Non-blocking

    def _copy_to_clipboard(self, text, dialog=None):
        """Copy text to clipboard and show feedback"""
        try:
            import pyperclip
            pyperclip.copy(text)
            self.signals.log.emit(f"<span style='color: #10B981;'>✓ Code copied to clipboard!</span>")
            if dialog:
                # Briefly change button text
                for btn in dialog.findChildren(QPushButton):
                    if "Copy" in btn.text():
                        original_text = btn.text()
                        btn.setText("✓ Copied!")
                        QTimer.singleShot(1500, lambda: btn.setText(original_text))
        except Exception as e:
            self.signals.log.emit(f"<span style='color: #EF4444;'>Failed to copy: {str(e)}</span>")

    def on_github_signin(self):
        """Handle GitHub Sign-In via OAuth Device Flow"""
        if not self.github_auth:
            self.signals.log.emit("<span style='color: #EF4444;'>GitHub Auth not initialized</span>")
            return

        try:
            self.signals.log.emit("🔗 Starting GitHub authentication...")
            self.github_signin_btn.setEnabled(False)
            self.github_signin_btn.setText("Signing in...")

            # Run sign-in in a separate thread to avoid blocking UI
            def sign_in_thread():
                def progress_callback(message, user_code=None, verification_url=None):
                    # Send progress with optional user code data
                    _from_companion_q.put(("GITHUB_PROGRESS", {
                        "message": message,
                        "user_code": user_code,
                        "verification_url": verification_url
                    }))

                print("🔄 Starting GitHub OAuth Device Flow...")
                result = self.github_auth.sign_in_with_browser(progress_callback=progress_callback)
                print(f"🔄 GitHub sign-in result: {result.get('success', False)}")
                # Update UI from main thread via queue
                _from_companion_q.put(("GITHUB_AUTH_RESULT", result))

            threading.Thread(target=sign_in_thread, daemon=True).start()

        except Exception as e:
            self.signals.log.emit(f"<span style='color: #EF4444;'>Error: {str(e)}</span>")
            self.github_signin_btn.setEnabled(True)
            self.github_signin_btn.setText("🔗 Sign in with GitHub")

    def on_google_signin(self):
        """Handle Google Sign-In"""
        if not self.firebase_auth:
            self.signals.log.emit("<span style='color: #EF4444;'>Firebase Auth not initialized. Create firebase_config.json</span>")
            return

        try:
            self.signals.log.emit("🔐 Opening Google Sign-In in your browser...")
            self.google_signin_btn.setEnabled(False)
            self.google_signin_btn.setText("Signing in...")

            # Run sign-in in a separate thread to avoid blocking UI
            def sign_in_thread():
                print("🔄 Starting Google sign-in...")
                result = self.firebase_auth.sign_in_with_google()
                print(f"🔄 Sign-in result: {result.get('success', False)}")
                # Update UI from main thread via queue
                _from_companion_q.put(("GOOGLE_AUTH_RESULT", result))

            threading.Thread(target=sign_in_thread, daemon=True).start()

        except Exception as e:
            self.signals.log.emit(f"<span style='color: #EF4444;'>Error: {str(e)}</span>")
            self.google_signin_btn.setEnabled(True)
            self.google_signin_btn.setText("🔐 Sign in with Google")

    def on_signout(self):
        """Handle user sign out"""
        if not self.firebase_auth:
            return

        try:
            result = self.firebase_auth.sign_out()
            if result['success']:
                self.signals.log.emit(f"<span style='color: #10B981;'>Signed out successfully</span>")
                self.signals.auth_clear.emit()
        except Exception as e:
            self.signals.log.emit(f"<span style='color: #EF4444;'>Error: {str(e)}</span>")

    def _update_auth_ui(self, user_data):
        """Update UI after successful authentication (runs in main thread via signal)"""
        print(f"🎨 _update_auth_ui called with user: {user_data.get('email', 'Anonymous')}")

        # Update user_id based on email for per-user memory separation
        if 'email' in user_data and user_data['email']:
            # Use email as user_id (sanitized)
            user_id = user_data['email'].replace('@', '_at_').replace('.', '_')
            self.user_id_display.setText(user_id)
            self.config['user_id'] = user_id
            self.auth_status_lbl.setText(f"AUTHENTICATED: {user_data['email']}")
        else:
            # Use anonymous user ID
            user_id = f"anonymous_{user_data.get('localId', 'unknown')[:8]}"
            self.user_id_display.setText(user_id)
            self.config['user_id'] = user_id
            self.auth_status_lbl.setText("AUTHENTICATED: Anonymous User")

        # CRITICAL: Update the running companion's user_id
        print(f"🔄 Updating companion user_id from config to: {user_id}")
        _to_companion_q.put(("UPDATE_CONFIG", {"user_id": user_id}))
        self.signals.log.emit(f"<span style='color: #10B981;'>🔄 Updated mem0 user_id to: {user_id}</span>")

        # Enable sign out button, disable sign in
        self.signout_btn.setEnabled(True)
        self.google_signin_btn.setEnabled(False)
        self.google_signin_btn.setText("✓ Signed In")

        # Display user info
        user_info = f"""<span style='color: #10B981; font-weight: 600;'>Authentication Successful!</span><br><br>"""
        if 'email' in user_data and user_data['email']:
            user_info += f"<span style='color: #D4D4D8;'><b>Email:</b> {user_data['email']}<br></span>"
        if 'displayName' in user_data and user_data['displayName']:
            user_info += f"<span style='color: #D4D4D8;'><b>Name:</b> {user_data['displayName']}<br></span>"
        user_info += f"<span style='color: #D4D4D8;'><b>User ID:</b> {user_data.get('localId', 'N/A')[:20]}...<br></span>"
        user_info += f"<span style='color: #71717A;'><b>Token Expires:</b> {user_data.get('expiresIn', 3600)} seconds</span>"

        self.user_info_area.setHtml(user_info)

        # Enable chat functionality now that user is authenticated
        self.update_chat_enabled_state()

        # Start the auto-refresh timer to keep the session alive
        self.start_auth_token_refresh_timer()

        # Switch to Account tab to show the updated UI
        self.tabs.setCurrentIndex(2)

        print(f"🎨 UI updated - Status: {self.auth_status_lbl.text()}")
        print(f"🎨 Sign out button enabled: {self.signout_btn.isEnabled()}")
        print(f"🎨 Google sign in button text: {self.google_signin_btn.text()}")

    def _clear_auth_ui(self):
        """Clear UI after sign out (runs in main thread via signal)"""
        self.auth_status_lbl.setText("Not authenticated")
        self.signout_btn.setEnabled(False)
        self.google_signin_btn.setEnabled(True)
        self.google_signin_btn.setText("🔐 Sign in with Google")
        self.user_info_area.clear()

        # Stop the auth refresh timer
        if self.auth_refresh_timer is not None and self.auth_refresh_timer.isActive():
            self.auth_refresh_timer.stop()
            print("🛑 Stopped auth refresh timer")

        # Reset to default user_id
        default_user_id = "default_user"
        self.user_id_display.setText(default_user_id)
        self.config['user_id'] = default_user_id

        # Update companion's user_id
        print(f"🔄 Resetting companion user_id to: {default_user_id}")
        _to_companion_q.put(("UPDATE_CONFIG", {"user_id": default_user_id}))

        # Disable chat functionality when signed out
        self.update_chat_enabled_state()

    def on_refresh_memories(self):
        """Request to load all memories from backend"""
        self.memory_status_lbl.setText("Loading...")
        self.memory_status_lbl.setStyleSheet("color: #60A5FA; font-size: 9px; margin-top: 4px;")
        _to_companion_q.put(("GET_MEMORIES", None))

    def on_memory_search(self):
        """Auto-search as user types (debounced by natural typing speed)"""
        # This is called on every text change, but we'll only search when user clicks Search button
        # or we could add a debounce timer here
        pass

    def on_memory_search_btn(self):
        """Handle search button click"""
        query = self.memory_search.text().strip()
        if query:
            self.memory_status_lbl.setText(f"Searching...")
            self.memory_status_lbl.setStyleSheet("color: #60A5FA; font-size: 9px; margin-top: 4px;")
            _to_companion_q.put(("SEARCH_MEMORIES", query))
        else:
            # If search is empty, refresh all memories
            self.on_refresh_memories()

    def on_delete_memory(self, memory_id):
        """Delete selected memory"""
        if memory_id:
            self.memory_status_lbl.setText(f"Deleting memory...")
            self.memory_status_lbl.setStyleSheet("color: #EF4444; font-size: 9px; margin-top: 4px;")
            _to_companion_q.put(("DELETE_MEMORY", memory_id))
        else:
            self.memory_status_lbl.setText("No memory selected")
            self.memory_status_lbl.setStyleSheet("color: #EF4444; font-size: 9px; margin-top: 4px;")

    def update_memories_display(self, memories):
        """Update the memories display with card-based layout"""
        # Clear existing cards
        while self.memories_cards_layout.count() > 1:  # Keep the stretch
            item = self.memories_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not memories:
            # Show empty state
            empty_label = QLabel("No memories found")
            empty_label.setObjectName("emptyStateLabel")
            empty_label.setStyleSheet("color: #52525B; font-size: 12px; padding: 40px; text-align: center;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.memories_cards_layout.insertWidget(0, empty_label)
            self.memory_status_lbl.setText("")
            return

        # Create card for each memory
        for memory in memories:
            # Extract memory data
            memory_id = memory.get('id', '')
            memory_text = memory.get('memory', '')
            created_at = memory.get('created_at', '')

            # Create memory card
            card = self.create_memory_card(memory_id, memory_text, created_at)
            self.memories_cards_layout.insertWidget(self.memories_cards_layout.count() - 1, card)

        self.memory_status_lbl.setText(f"{len(memories)} memories")
        self.memory_status_lbl.setStyleSheet("color: #71717A; font-size: 9px; margin-top: 4px;")

    def create_memory_card(self, memory_id, memory_text, created_at):
        """Create a minimalist card widget for a single memory"""
        card = QFrame()
        card.setObjectName("memoryCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        # Top row: timestamp and delete button
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Minimalist timestamp
        if created_at:
            # Parse and format timestamp more minimally
            from datetime import datetime
            try:
                # Try to parse ISO format
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                # Format as relative time or simple date
                now = datetime.now(dt.tzinfo)
                diff = now - dt
                if diff.days == 0:
                    time_str = dt.strftime("%H:%M")
                elif diff.days == 1:
                    time_str = "Yesterday"
                elif diff.days < 7:
                    time_str = f"{diff.days}d ago"
                else:
                    time_str = dt.strftime("%b %d")
            except:
                time_str = created_at[:10] if len(created_at) > 10 else created_at
        else:
            time_str = ""

        timestamp_lbl = QLabel(time_str)
        timestamp_lbl.setObjectName("memoryTimestamp")
        timestamp_lbl.setStyleSheet("color: #52525B; font-size: 9px; font-weight: 500;")
        top_row.addWidget(timestamp_lbl)

        top_row.addStretch()

        # Delete button (minimalist)
        delete_btn = QPushButton("×")
        delete_btn.setObjectName("memoryDeleteBtn")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setFixedSize(20, 20)
        delete_btn.setToolTip("Delete memory")
        delete_btn.clicked.connect(lambda checked, mid=memory_id: self.on_delete_memory(mid))
        top_row.addWidget(delete_btn)

        card_layout.addLayout(top_row)

        # Memory text with word wrap
        text_lbl = QLabel(memory_text)
        text_lbl.setObjectName("memoryText")
        text_lbl.setWordWrap(True)
        text_lbl.setStyleSheet("color: #D4D4D8; font-size: 12px; line-height: 1.5;")
        card_layout.addWidget(text_lbl)

        return card

    def append_log(self, text: str):
        # Log area removed - logs are no longer displayed
        pass

    def set_status(self, text: str):
        self.status_lbl.setText(text)
        # Update status dot color based on state - DISABLED (dot removed)
        # if text.lower() in ["recording", "active"]:
        #     self.status_dot.setStyleSheet("color: #10B981; font-size: 16px;")
        # elif "error" in text.lower():
        #     self.status_dot.setStyleSheet("color: #EF4444; font-size: 16px;")
        # else:
        #     self.status_dot.setStyleSheet("color: #71717A; font-size: 16px;")

    def append_progress(self, event_type: str, data: dict):
        """Add progress indicator to response area"""
        # Add header for first progress event
        if event_type == "MEMORY_SEARCH" and not hasattr(self, '_progress_started'):
            self._progress_started = True
            ts = time.strftime("%H:%M:%S")
            header = (
                f"<div style='margin-top: 12px; margin-bottom: 8px; padding: 8px 0; "
                f"border-top: 1px solid rgba(255,255,255,0.08); border-bottom: 1px solid rgba(255,255,255,0.08);'>"
                f"<span style='color: #60A5FA; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;'>"
                f"⚙️ PROCESSING [{ts}]</span></div>"
            )
            self.response_area.append(header)

        # Reset flag on answer ready
        if event_type == "ANSWER_READY":
            self._progress_started = False
            # Add separator after progress
            self.response_area.append("<br>")

        progress_html = format_progress_html(event_type, data)
        self.response_area.append(progress_html)

        # Auto-scroll to bottom
        cursor = self.response_area.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.response_area.setTextCursor(cursor)

    def append_response(self, text: str):
        ts = time.strftime("%H:%M:%S")
        # Convert markdown to HTML for display
        html_content = convert_markdown_to_html(text)

        # Create formatted HTML for display
        html_display = (
            f"<div style='margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.04);'>"
            f"<span style='color: #71717A; font-size: 10px; font-weight: 500;'>[{ts}]</span>"
            f"<div style='color: #FAFAFA; line-height: 1.6; margin-top: 8px;'>{html_content}</div>"
            f"</div>"
        )

        # Store original markdown with timestamp
        markdown_with_ts = f"[{ts}]\n{text}"

        # Add both versions to the custom text edit
        self.response_area.add_markdown_message(markdown_with_ts, html_display)

    def clear_response_and_progress(self):
        """Clear both response and progress indicators"""
        self.response_area.clear_messages()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()

    # Dragging behavior
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() if hasattr(ev, "globalPosition") else ev.globalPos()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag_pos:
            current_pos = ev.globalPosition().toPoint() if hasattr(ev, "globalPosition") else ev.globalPos()
            diff = current_pos - self._drag_pos
            self.move(self.x() + diff.x(), self.y() + diff.y())
            self._drag_pos = current_pos
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None
        super().mouseReleaseEvent(ev)

    # Polling queue from companion runner
    def start_polling_companion_queue(self):
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll_companion_queue)
        self.poll_timer.start(150)

    def start_auth_token_refresh_timer(self):
        """Start a timer to automatically refresh auth tokens before they expire"""
        if not self.firebase_auth:
            return

        # Only start if authenticated
        if not self.firebase_auth.is_authenticated():
            return

        # Stop existing timer if running
        if self.auth_refresh_timer is not None:
            if self.auth_refresh_timer.isActive():
                self.auth_refresh_timer.stop()

        self.auth_refresh_timer = QTimer()
        self.auth_refresh_timer.timeout.connect(self.check_and_refresh_auth_token)
        # Check every 30 minutes (tokens expire in 60 minutes)
        self.auth_refresh_timer.start(30 * 60 * 1000)  # 30 minutes in milliseconds
        print("🔄 Started auto-refresh timer (refreshes every 30 minutes)")

    def check_and_refresh_auth_token(self):
        """Check if auth token needs refresh and refresh if necessary"""
        if not self.firebase_auth or not self.firebase_auth.is_authenticated():
            return

        try:
            # Always refresh to keep session alive
            result = self.firebase_auth.refresh_token()
            if result['success']:
                print("🔄 Auto-refreshed authentication token")
                self.signals.log.emit("<span style='color: #60A5FA;'>🔄 Authentication refreshed</span>")
            else:
                print(f"⚠️ Auto-refresh failed: {result['message']}")
                # If refresh fails, user needs to sign in again
                self.signals.auth_clear.emit()
                self.signals.log.emit("<span style='color: #EF4444;'>⚠️ Session expired. Please sign in again.</span>")
        except Exception as e:
            print(f"⚠️ Auto-refresh error: {e}")

    def poll_companion_queue(self):
        # Take messages from _from_companion_q and apply to UI
        changed = False
        while True:
            try:
                typ, payload = _from_companion_q.get_nowait()
            except Empty:
                break
            changed = True
            print(f"🔔 Queue received message type: {typ}")
            if typ == "STARTED":
                self._is_recording = True
                self.recording_status_label.setText("🔴 Recording Active")
                self.recording_status_label.setStyleSheet("""
                    QLabel {
                        color: #10B981;
                        font-size: 12px;
                        font-weight: 600;
                        padding: 8px 12px;
                        background-color: rgba(16, 185, 129, 0.1);
                        border-radius: 6px;
                    }
                """)
                self.signals.status.emit("Recording")
                self.signals.log.emit(str(payload))
            elif typ == "STOPPED":
                # Recording should always be active - if stopped, restart it
                self._is_recording = False
                self.recording_status_label.setText("⚠️ Recording Paused")
                self.recording_status_label.setStyleSheet("""
                    QLabel {
                        color: #F59E0B;
                        font-size: 12px;
                        font-weight: 600;
                        padding: 8px 12px;
                        background-color: rgba(245, 158, 11, 0.1);
                        border-radius: 6px;
                    }
                """)
                self.signals.status.emit("Paused")
                self.signals.log.emit(str(payload))
                # Auto-restart if authenticated
                if self.firebase_auth and self.firebase_auth.is_authenticated():
                    QTimer.singleShot(1000, self.auto_start_recording)
            elif typ == "RESPONSE":
                # Handle structured response (dict with display/gemini_raw) or plain string
                response_text = ""
                if isinstance(payload, dict) and "display" in payload:
                    response_text = payload["display"]
                    self.signals.response.emit(response_text)
                else:
                    response_text = str(payload)
                    self.signals.response.emit(response_text)

                # Save chat to Firestore
                self._save_chat_to_firestore(response_text)
            elif typ == "ERROR":
                self.signals.log.emit("<span style='color: #EF4444;'>[ERROR]</span> " + str(payload))
            elif typ == "CONFIG_UPDATED":
                self.signals.log.emit("<span style='color: #10B981;'>Companion config updated.</span>")
            elif typ == "PROGRESS":
                # Handle progress updates from backend
                event_type, data = payload
                self.append_progress(event_type, data)
            elif typ == "GITHUB_PROGRESS":
                # Handle GitHub authentication progress updates
                if isinstance(payload, dict):
                    message = payload.get("message", "")
                    user_code = payload.get("user_code")
                    verification_url = payload.get("verification_url")

                    # Show user code in a dialog if provided
                    if user_code and verification_url:
                        self._show_github_user_code_dialog(user_code, verification_url)

                    self.signals.log.emit(f"<span style='color: #60A5FA;'>{message}</span>")
                else:
                    # Fallback for string messages
                    self.signals.log.emit(f"<span style='color: #60A5FA;'>{payload}</span>")
            elif typ == "GITHUB_AUTH_RESULT":
                # Handle GitHub auth result
                print(f"📥 Received GITHUB_AUTH_RESULT in UI thread")
                result = payload
                if result['success']:
                    print(f"✅ GitHub Sign-In successful: {result['user']}")
                    self.signals.log.emit(f"<span style='color: #10B981;'>✅ {result['message']}</span>")

                    # Update button
                    self.github_signin_btn.setEnabled(False)
                    self.github_signin_btn.setText("✓ Connected to GitHub")

                    # Update user label
                    self.github_user_lbl.setText(f"Connected as: {result['user']}")
                    self.github_user_lbl.setStyleSheet("color: #10B981; font-size: 11px; margin-top: 8px;")
                else:
                    print(f"❌ GitHub Sign-In failed: {result['message']}")
                    self.signals.log.emit(f"<span style='color: #EF4444;'>GitHub Sign-In failed: {result['message']}</span>")
                    self.github_signin_btn.setEnabled(True)
                    self.github_signin_btn.setText("🔗 Sign in with GitHub")
            elif typ == "GOOGLE_AUTH_RESULT":
                # Handle Google auth result
                print(f"📥 Received GOOGLE_AUTH_RESULT in UI thread")
                result = payload
                if result['success']:
                    print(f"✅ Google Sign-In successful, restarting app...")
                    # Show restart message
                    self.signals.log.emit(f"<span style='color: #10B981;'>{result['message']}</span>")
                    self.signals.log.emit(f"<span style='color: #60A5FA;'>🔄 Restarting app to apply authentication...</span>")

                    # Update button to show restart state
                    self.google_signin_btn.setEnabled(False)
                    self.google_signin_btn.setText("🔄 Restarting...")

                    # Switch to Auth tab to show status
                    self.tabs.setCurrentIndex(2)

                    # Update auth status label
                    self.auth_status_lbl.setText(f"✅ AUTHENTICATED - Restarting app...")

                    # Show info in user area
                    restart_msg = """<span style='color: #10B981; font-weight: 600; font-size: 16px;'>✓ Authentication Successful!</span><br><br>
                    <span style='color: #60A5FA; font-size: 14px;'>🔄 Restarting application...</span><br><br>
                    <span style='color: #A1A1AA; font-size: 12px;'>The app will restart automatically to load your authenticated session.</span>"""
                    self.user_info_area.setHtml(restart_msg)

                    # Restart the app after short delay
                    QTimer.singleShot(2000, self.restart_application)
                else:
                    print(f"❌ Google Sign-In failed: {result['message']}")
                    self.signals.log.emit(f"<span style='color: #EF4444;'>Google Sign-In failed: {result['message']}</span>")
                    self.google_signin_btn.setEnabled(True)
                    self.google_signin_btn.setText("🔐 Sign in with Google")
            elif typ == "CHAT_HISTORY_LOADED":
                # Handle chat history loaded from Firestore
                chats = payload
                self.display_chat_history(chats)
            elif typ == "MEMORIES_LIST":
                # Handle memories list response
                memories = payload
                self.update_memories_display(memories)
            elif typ == "SEARCH_RESULTS":
                # Handle search results
                memories = payload
                self.update_memories_display(memories)
            elif typ == "DELETE_SUCCESS":
                # Handle delete success
                success = payload
                if success:
                    self.memory_status_lbl.setText("Deleted")
            elif typ == "UPDATE_AVAILABLE":
                # Handle update available notification
                update_info = payload
                self._show_update_notification(update_info)
            elif typ == "UPDATE_PROGRESS":
                # Handle update download/install progress
                stage, data = payload
                if hasattr(self, 'update_progress_bar') and hasattr(self, 'update_status_label'):
                    if stage == 'download_progress':
                        percent = data.get('percent', 0)
                        self.update_progress_bar.setValue(int(percent))
                        self.update_status_label.setText(f"Downloading... {int(percent)}%")
                    elif stage == 'installing':
                        self.update_progress_bar.setValue(100)
                        self.update_status_label.setText("Installing update...")
                    elif stage == 'complete':
                        self.update_status_label.setText("✓ Update installed! Restarting...")
                        QTimer.singleShot(2000, lambda: sys.exit(0))
                    elif stage == 'error':
                        self.update_status_label.setText(f"❌ {data.get('message', 'Update failed')}")
                        self.update_status_label.setStyleSheet("color: #EF4444;")
                    self.memory_status_lbl.setStyleSheet("color: #10B981; font-size: 9px; margin-top: 4px;")
                    # Refresh the list after deletion
                    self.on_refresh_memories()
                else:
                    self.memory_status_lbl.setText("Delete failed")
                    self.memory_status_lbl.setStyleSheet("color: #EF4444; font-size: 9px; margin-top: 4px;")
            else:
                self.signals.log.emit(f"[{typ}] {payload}")

        # If the runner reported instantiation error earlier, show it
        if self.runner and self.runner.last_error:
            self.signals.log.emit("<span style='color: #EF4444;'>Runner instantiation error:</span> " + str(self.runner.last_error))
            self.runner.last_error = None

    def restart_application(self):
        """Restart the application to reload authenticated state"""
        print("🔄 Restarting application...")
        # Close current app gracefully
        _to_companion_q.put(("SHUTDOWN", None))
        time.sleep(0.1)

        # Restart using the same Python executable and script
        python_exec = sys.executable
        script_path = sys.argv[0]

        # Close the current app and start a new instance
        subprocess.Popen([python_exec, script_path] + sys.argv[1:])
        QApplication.quit()

    def closeEvent(self, ev):
        # Attempt clean shutdown of companion
        _to_companion_q.put(("SHUTDOWN", None))
        time.sleep(0.2)
        ev.accept()


def load_config():
    default = {
        "api_key": "",
        "user_id": "default_user",
        "interval": 10,
        "watch_dirs": [],
        "always_recent": 3,
        "qa_model": "gemini",
        "onboarding_completed": False
    }
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                conf = json.load(f)
            default.update(conf)
    except Exception:
        pass
    return default


def companion_queue_forwarder():
    """
    This separate thread watches _from_companion_q and forwards items into the runner->ui queue.
    Not strictly necessary, but kept for potential extension points. Currently unused.
    """
    while True:
        time.sleep(0.5)
        # placeholder


def save_config_to_file(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[WARNING] Failed to save config: {e}")


def main():
    config = load_config()
    app = QApplication(sys.argv)

    # Initialize Firebase Auth first
    firebase_auth = None
    if FIREBASE_AVAILABLE:
        try:
            # Use embedded Firebase configuration to avoid external files
            embedded_firebase_config = {
              "apiKey": "AIzaSyBsig0QxBmVelZQwef23-MoTFdeuZM5P-4",
              "authDomain": "ghost-widget-7000.firebaseapp.com",
              "projectId": "ghost-widget-7000",
              "databaseURL": "https://ghost-widget-7000-default-rtdb.firebaseio.com/",
              "storageBucket": "ghost-widget-7000.firebasestorage.app",
              "google_client_id": "816342083028-te98svps0mjo5230g3aasfipt8qr824g.apps.googleusercontent.com",
              "google_client_secret": "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",
              "messagingSenderId": "816342083028",
              "appId": "1:816342083028:web:0e0d8aa40d66bf858f2241",
              "measurementId": "G-XGLGL9E2TJ"
            }

            firebase_auth = FirebaseAuth(config=embedded_firebase_config, persist_auth=True)
            print("✅ Firebase Auth initialized")
        except Exception as e:
            print(f"❌ Failed to initialize Firebase Auth: {e}")
            QMessageBox.critical(
                None,
                "Authentication Error",
                f"Failed to initialize authentication: {e}"
            )
            sys.exit(1)
    else:
        QMessageBox.critical(
            None,
            "Missing Dependencies",
            "Firebase authentication libraries not installed. Please contact support."
        )
        sys.exit(1)

    # Initialize GitHub Auth
    github_auth = None
    if GITHUB_AVAILABLE:
        try:
            github_auth = get_github_auth()
            print("✅ GitHub Auth initialized")
        except Exception as e:
            print(f"⚠️ GitHub Auth initialization warning: {e}")

    # Check if onboarding is needed OR if user is not authenticated
    needs_onboarding = not config.get("onboarding_completed", False)
    is_authenticated = firebase_auth and firebase_auth.is_authenticated()

    # Show onboarding if needed or not authenticated (no blocking dialogs)
    if needs_onboarding or not is_authenticated:
        from onboarding import OnboardingDialog

        onboarding = OnboardingDialog(
            firebase_auth=firebase_auth,
            github_auth=github_auth
        )
        result = onboarding.exec()

        if result == OnboardingDialog.DialogCode.Accepted:
            # Mark onboarding as completed
            config["onboarding_completed"] = True
            save_config_to_file(config)
            print("[OK] Onboarding completed")
        else:
            # User cancelled onboarding - exit app
            print("[INFO] User cancelled onboarding. Exiting.")
            sys.exit(0)

        # Verify authentication after onboarding
        if not firebase_auth.is_authenticated():
            print("[ERROR] Authentication failed. Exiting.")
            sys.exit(1)

    # Log GitHub status (no blocking dialog)
    if github_auth and github_auth.is_authenticated():
        print("✅ GitHub connected")
    else:
        print("ℹ️ GitHub not connected - some features will be limited")

    w = OverlayWindow(config)

    # Position window on right-center of the screen
    screen = app.primaryScreen()
    geo = screen.availableGeometry()
    w.move(geo.x() + geo.width() - w.width() - 40, geo.y() + (geo.height() - w.height()) // 2)
    w.show()

    # Start the global hotkey listener in a daemon thread
    hk_thread = threading.Thread(target=hotkey_listener, daemon=True, name="HotkeyThread")
    hk_thread.start()

    # Poll the queue every few ms to toggle visibility
    def poll_hotkey_queue():
        try:
            while not _hotkey_queue.empty():
                msg = _hotkey_queue.get_nowait()
                if msg[0] == "TOGGLE_VISIBILITY":
                    if w.isVisible():
                        w.hide()
                    else:
                        w.show()
        except Exception as e:
            print("Hotkey queue error:", e)

    hotkey_timer = QTimer()
    hotkey_timer.timeout.connect(poll_hotkey_queue)
    hotkey_timer.start(100)

    print(f"Global hotkey listener started ({HOTKEY_COMBO}) to toggle overlay visibility.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()