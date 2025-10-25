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

USE_PYQT6 = True
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSpinBox,
    QGraphicsDropShadowEffect, QTabWidget, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, pyqtSignal, QObject, QPropertyAnimation, QEasingCurve, QMimeData
from PyQt6.QtGui import QFont, QAction, QColor

from pynput import keyboard

HOTKEY_COMBO = "<ctrl>+<alt>+`"   # you can change this to whatever you want

_hotkey_queue = Queue()

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
        return f"<span style='color: #60A5FA; font-size: 11px;'>💬 AI processing...</span>"
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
            "capture_interval": self.config.get("interval", 10),
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
                question = payload
                resp = self._call_ask(question)
                _from_companion_q.put(("RESPONSE", resp))
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

    def _call_ask(self, question: str):
        if not self.companion:
            return "Companion not instantiated."
        # Try expected names: ask, query, ask_gemini, send_prompt
        for method_name in ("ask", "query", "ask_gemini", "send_prompt", "chat"):
            if hasattr(self.companion, method_name):
                try:
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

        self.init_ui()
        self.start_polling_companion_queue()
        self.start_auth_token_refresh_timer()

    def _init_firebase_auth(self):
        """Initialize Firebase Auth if config file exists"""
        if not FIREBASE_AVAILABLE:
            return

        try:
            config_path = Path("firebase_config.json")
            if config_path.exists():
                self.firebase_auth = FirebaseAuth(config_file="firebase_config.json", persist_auth=True)
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
            else:
                print("Firebase config not found. Create firebase_config.json to enable authentication.")
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

    def update_github_ui_state(self, username):
        """Update GitHub UI to show authenticated state"""
        if hasattr(self, 'github_signin_btn') and hasattr(self, 'github_user_lbl'):
            self.github_signin_btn.setEnabled(False)
            self.github_signin_btn.setText("✓ Connected to GitHub")
            self.github_user_lbl.setText(f"Connected as: {username}")
            self.github_user_lbl.setStyleSheet("color: #10B981; font-size: 11px; margin-top: 8px;")

    def init_ui(self):
        self.setWindowTitle("Ghost Widget")
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

        # Status indicator dot
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status_dot.setStyleSheet("color: #6B7280; font-size: 16px;")
        title_h.addWidget(self.status_dot)

        title_lbl = QLabel("Ghost Widget")
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

        # Buttons: Start/Stop with compact design
        btn_h = QHBoxLayout()
        btn_h.setSpacing(8)

        self.start_btn = QPushButton("Start Recording")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.on_start_stop)
        self.start_btn.setFixedHeight(32)
        btn_h.addWidget(self.start_btn, 2)

        self.hide_btn = QPushButton("Hide")
        self.hide_btn.setObjectName("secondaryButton")
        self.hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_btn.clicked.connect(self.toggle_visibility)
        self.hide_btn.setFixedHeight(32)
        btn_h.addWidget(self.hide_btn, 1)
        chat_layout.addLayout(btn_h)

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

        # Interval spinner with modern styling
        interval_h = QHBoxLayout()
        interval_h.setSpacing(16)
        interval_label = QLabel("Capture Interval")
        interval_label.setObjectName("fieldLabel")
        interval_h.addWidget(interval_label)

        self.interval_spin = QSpinBox()
        self.interval_spin.setObjectName("modernSpinBox")
        self.interval_spin.setRange(1, 86400)
        self.interval_spin.setValue(int(self.config.get("interval", 10)))
        self.interval_spin.setSuffix(" sec")
        self.interval_spin.setFixedHeight(38)
        self.interval_spin.setFixedWidth(125)
        interval_h.addWidget(self.interval_spin)
        interval_h.addStretch()
        settings_layout.addLayout(interval_h)

        # QA Model selection with modern styling
        qa_model_h = QHBoxLayout()
        qa_model_h.setSpacing(16)
        qa_model_label = QLabel("QA Model")
        qa_model_label.setObjectName("fieldLabel")
        qa_model_label.setToolTip("Model used for answering questions (screenshots always use Gemini)")
        qa_model_h.addWidget(qa_model_label)

        self.qa_model_combo = QComboBox()
        self.qa_model_combo.setObjectName("modernComboBox")
        self.qa_model_combo.addItem("Gemini (Default)", "gemini")
        self.qa_model_combo.addItem("Claude 4.5 Sonnet", "claude")
        self.qa_model_combo.setToolTip("Gemini: Free/low-cost, fast\nClaude: Superior reasoning, requires Vertex AI setup")

        # Set current value from config
        current_qa_model = self.config.get("qa_model", "gemini")
        index = self.qa_model_combo.findData(current_qa_model)
        if index >= 0:
            self.qa_model_combo.setCurrentIndex(index)

        self.qa_model_combo.setFixedHeight(38)
        self.qa_model_combo.setFixedWidth(200)
        qa_model_h.addWidget(self.qa_model_combo)
        qa_model_h.addStretch()
        settings_layout.addLayout(qa_model_h)

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
        """)

    def on_add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select directory to watch")
        if d:
            self.watch_list.addItem(QListWidgetItem(d))

    def on_remove_dir(self):
        for item in list(self.watch_list.selectedItems()):
            self.watch_list.takeItem(self.watch_list.row(item))

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
            "interval": int(self.interval_spin.value()),
            "watch_dirs": watch_dirs,
            "always_recent": self.config.get("always_recent", 3),
            "qa_model": self.qa_model_combo.currentData()
        }

    def on_start_stop(self):
        if not self._is_recording:
            # send START
            _to_companion_q.put(("START", None))
            self.signals.log.emit("Requested start.")
        else:
            _to_companion_q.put(("STOP", None))
            self.signals.log.emit("Requested stop.")

    def update_chat_enabled_state(self):
        """Enable or disable chat based on authentication status"""
        is_authenticated = bool(self.firebase_auth and self.firebase_auth.is_authenticated())

        # Enable/disable chat input and button
        self.ask_edit.setEnabled(is_authenticated)
        self.ask_btn.setEnabled(is_authenticated)
        self.start_btn.setEnabled(is_authenticated)

        # Update placeholder text
        if not is_authenticated:
            self.ask_edit.setPlaceholderText("Sign in to use chat")
            self.response_area.setPlaceholderText("Please sign in to your Google account to use chat features")
        else:
            self.ask_edit.setPlaceholderText("Ask Anything")
            self.response_area.setPlaceholderText("")

    def on_ask(self):
        # Check authentication before allowing chat
        if not (self.firebase_auth and self.firebase_auth.is_authenticated()):
            return

        q = self.ask_edit.text().strip()
        if not q:
            return
        _to_companion_q.put(("ASK", q))
        # optionally clear input
        self.ask_edit.clear()

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
                def progress_callback(message):
                    _from_companion_q.put(("GITHUB_PROGRESS", message))

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

    def append_log(self, text: str):
        # Log area removed - logs are no longer displayed
        pass

    def set_status(self, text: str):
        self.status_lbl.setText(text)
        # Update status dot color based on state
        if text.lower() in ["recording", "active"]:
            self.status_dot.setStyleSheet("color: #10B981; font-size: 16px;")
        elif "error" in text.lower():
            self.status_dot.setStyleSheet("color: #EF4444; font-size: 16px;")
        else:
            self.status_dot.setStyleSheet("color: #71717A; font-size: 16px;")

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
                self.start_btn.setText("Stop Recording")
                self.start_btn.setObjectName("stopButton")
                self.start_btn.setStyleSheet("""
                    #stopButton {
                        background: qlineargradient(
                            x1:0, y1:0, x2:1, y2:0,
                            stop:0 #EF4444,
                            stop:1 #DC2626
                        );
                        color: white;
                        border: none;
                        border-radius: 10px;
                        font-weight: 600;
                        font-size: 13px;
                        padding: 0 20px;
                    }
                    #stopButton:hover {
                        background: qlineargradient(
                            x1:0, y1:0, x2:1, y2:0,
                            stop:0 #DC2626,
                            stop:1 #B91C1C
                        );
                    }
                    #stopButton:pressed {
                        background: #991B1B;
                    }
                """)
                self.signals.status.emit("Recording")
                self.signals.log.emit(str(payload))
            elif typ == "STOPPED":
                self._is_recording = False
                self.start_btn.setText("Start Recording")
                self.start_btn.setObjectName("primaryButton")
                self.start_btn.setStyleSheet("")  # Reset to default
                self.signals.status.emit("Idle")
                self.signals.log.emit(str(payload))
            elif typ == "RESPONSE":
                # Could be complex object; coerce to str
                self.signals.response.emit(str(payload))
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
                message = payload
                self.signals.log.emit(f"<span style='color: #60A5FA;'>{message}</span>")
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
        "qa_model": "gemini"
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


def main():
    config = load_config()
    app = QApplication(sys.argv)
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