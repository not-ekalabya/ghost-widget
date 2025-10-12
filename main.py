#!/usr/bin/env python3
"""
Modern Overlay app that wraps BackgroundCompanion from main.py

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

USE_PYQT6 = True
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem, QFileDialog, QMessageBox, QSpinBox,
    QGraphicsDropShadowEffect, QTabWidget
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

        # Pass directly to the class
        kwargs = {
            "api_key": HARD_CODED_API_KEY,
            "capture_interval": self.config.get("interval", 60),
            "watch_dirs": self.config.get("watch_dirs", []),
            "always_recent": self.config.get("always_recent", 3)
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
                    except Exception:
                        pass


# ---------- Qt UI components ----------
class Signals(QObject):
    # simple signal container
    log = pyqtSignal(str)
    status = pyqtSignal(str)
    response = pyqtSignal(str)
    config_saved = pyqtSignal()


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

        self.config = config
        self.runner = CompanionRunner(self.config)
        self.runner.start()  # instantiate companion immediately in thread (non-blocking)

        self._drag_pos = None
        self._is_recording = False

        self.init_ui()
        self.start_polling_companion_queue()

    def init_ui(self):
        self.setWindowTitle("Background Companion")
        # Visual sizing - compact for tabs
        self.setFixedSize(440, 580)

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

        title_lbl = QLabel("Background Companion")
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
        chat_layout.setContentsMargins(0, 16, 0, 0)
        chat_layout.setSpacing(16)

        # Buttons: Start/Stop with modern design
        btn_h = QHBoxLayout()
        btn_h.setSpacing(10)

        self.start_btn = QPushButton("Start Recording")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self.on_start_stop)
        self.start_btn.setFixedHeight(46)
        btn_h.addWidget(self.start_btn, 2)

        self.hide_btn = QPushButton("Hide")
        self.hide_btn.setObjectName("secondaryButton")
        self.hide_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_btn.clicked.connect(self.toggle_visibility)
        self.hide_btn.setFixedHeight(46)
        btn_h.addWidget(self.hide_btn, 1)
        chat_layout.addLayout(btn_h)

        # Ask question section with modern input
        ask_section = QVBoxLayout()
        ask_section.setSpacing(8)

        ask_lbl = QLabel("ASK QUESTION")
        ask_lbl.setObjectName("sectionLabel")
        ask_section.addWidget(ask_lbl)

        ask_input_h = QHBoxLayout()
        ask_input_h.setSpacing(10)

        self.ask_edit = QLineEdit()
        self.ask_edit.setObjectName("modernInput")
        self.ask_edit.setPlaceholderText("What would you like to know?")
        self.ask_edit.returnPressed.connect(self.on_ask)
        self.ask_edit.setFixedHeight(42)
        ask_input_h.addWidget(self.ask_edit)

        self.ask_btn = QPushButton("Send")
        self.ask_btn.setObjectName("accentButton")
        self.ask_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ask_btn.clicked.connect(self.on_ask)
        self.ask_btn.setFixedHeight(42)
        self.ask_btn.setFixedWidth(85)
        ask_input_h.addWidget(self.ask_btn)

        ask_section.addLayout(ask_input_h)
        chat_layout.addLayout(ask_section)

        # Response display with header
        resp_header = QHBoxLayout()
        resp_header.setSpacing(0)
        resp_lbl = QLabel("")
        resp_lbl.setObjectName("sectionLabel")
        resp_header.addWidget(resp_lbl)
        resp_header.addStretch()

        self.clear_resp_btn = QPushButton("Clear")
        self.clear_resp_btn.setObjectName("textButton")
        self.clear_resp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_resp_btn.clicked.connect(lambda: self.response_area.clear())
        self.clear_resp_btn.setFixedHeight(24)
        resp_header.addWidget(self.clear_resp_btn)
        content.addLayout(resp_header)

        self.response_area = MarkdownTextEdit()
        self.response_area.setObjectName("modernTextArea")
        self.response_area.setReadOnly(True)
        chat_layout.addWidget(self.response_area)

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

        # API Key with save button
        cfg_form_h = QHBoxLayout()
        cfg_form_h.setSpacing(10)

        self.api_key_edit = QLineEdit(self.config.get("api_key", ""))
        self.api_key_edit.setObjectName("modernInput")
        self.api_key_edit.setPlaceholderText("API Key (optional)")
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setFixedHeight(38)
        cfg_form_h.addWidget(self.api_key_edit)

        self.save_cfg_btn = QPushButton("Save")
        self.save_cfg_btn.setObjectName("accentButton")
        self.save_cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_cfg_btn.clicked.connect(self.save_config)
        self.save_cfg_btn.setFixedHeight(38)
        self.save_cfg_btn.setFixedWidth(75)
        cfg_form_h.addWidget(self.save_cfg_btn)
        settings_layout.addLayout(cfg_form_h)

        # Interval spinner with modern styling
        interval_h = QHBoxLayout()
        interval_h.setSpacing(16)
        interval_label = QLabel("Capture Interval")
        interval_label.setObjectName("fieldLabel")
        interval_h.addWidget(interval_label)

        self.interval_spin = QSpinBox()
        self.interval_spin.setObjectName("modernSpinBox")
        self.interval_spin.setRange(1, 86400)
        self.interval_spin.setValue(int(self.config.get("interval", 60)))
        self.interval_spin.setSuffix(" sec")
        self.interval_spin.setFixedHeight(38)
        self.interval_spin.setFixedWidth(125)
        interval_h.addWidget(self.interval_spin)
        interval_h.addStretch()
        settings_layout.addLayout(interval_h)

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

        # Log area
        log_lbl = QLabel("ACTIVITY LOG")
        log_lbl.setObjectName("sectionLabel")
        settings_layout.addWidget(log_lbl)

        self.log_area = QTextEdit()
        self.log_area.setObjectName("modernTextArea")
        self.log_area.setReadOnly(True)
        settings_layout.addWidget(self.log_area)
        settings_layout.addStretch()

        # Add settings tab
        self.tabs.addTab(settings_tab, "Settings")

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

    def apply_modern_style(self):
        self.setStyleSheet("""
            /* Main container with glassmorphism effect */
            #container {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(24, 24, 27, 0.98),
                    stop:1 rgba(18, 18, 21, 0.98)
                );
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.06);
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
            
            /* Primary button - gradient with hover effect */
            #primaryButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563EB,
                    stop:1 #1D4ED8
                );
                color: #FFFFFF;
                border: none;
                border-radius: 12px;
                font-weight: 600;
                font-size: 14px;
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
                border-radius: 12px;
                font-weight: 500;
                font-size: 13px;
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
                border-radius: 10px;
                font-weight: 600;
                font-size: 13px;
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
                border-radius: 10px;
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

            /* Text areas */
            #modernTextArea {
                background: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
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
                border-radius: 10px;
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
            
            /* List widget */
            #modernList {
                background: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
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

            /* Tab Widget */
            QTabWidget::pane {
                border: none;
                background: transparent;
                margin-top: 0px;
            }

            QTabBar::tab {
                background: rgba(255, 255, 255, 0.04);
                color: #71717A;
                border: none;
                border-radius: 10px 10px 0 0;
                padding: 12px 24px;
                margin-right: 4px;
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.3px;
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
            "api_key": self.api_key_edit.text().strip(),
            "interval": int(self.interval_spin.value()),
            "watch_dirs": watch_dirs,
            "always_recent": self.config.get("always_recent", 3)
        }

    def on_start_stop(self):
        if not self._is_recording:
            # send START
            _to_companion_q.put(("START", None))
            self.signals.log.emit("Requested start.")
        else:
            _to_companion_q.put(("STOP", None))
            self.signals.log.emit("Requested stop.")

    def on_ask(self):
        q = self.ask_edit.text().strip()
        if not q:
            return
        self.signals.log.emit(f"> {q}")
        _to_companion_q.put(("ASK", q))
        # optionally clear input
        self.ask_edit.clear()

    def append_log(self, text: str):
        ts = time.strftime("%H:%M:%S")
        self.log_area.append(f"<span style='color: #71717A; font-size: 10px;'>[{ts}]</span> <span style='color: #D4D4D8;'>{text}</span>")

    def set_status(self, text: str):
        self.status_lbl.setText(text)
        # Update status dot color based on state
        if text.lower() in ["recording", "active"]:
            self.status_dot.setStyleSheet("color: #10B981; font-size: 16px;")
        elif "error" in text.lower():
            self.status_dot.setStyleSheet("color: #EF4444; font-size: 16px;")
        else:
            self.status_dot.setStyleSheet("color: #71717A; font-size: 16px;")

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

    def poll_companion_queue(self):
        # Take messages from _from_companion_q and apply to UI
        changed = False
        while True:
            try:
                typ, payload = _from_companion_q.get_nowait()
            except Empty:
                break
            changed = True
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
            else:
                self.signals.log.emit(f"[{typ}] {payload}")

        # If the runner reported instantiation error earlier, show it
        if self.runner and self.runner.last_error:
            self.signals.log.emit("<span style='color: #EF4444;'>Runner instantiation error:</span> " + str(self.runner.last_error))
            self.runner.last_error = None

    def closeEvent(self, ev):
        # Attempt clean shutdown of companion
        _to_companion_q.put(("SHUTDOWN", None))
        time.sleep(0.2)
        ev.accept()


def load_config():
    default = {
        "api_key": "",
        "interval": 60,
        "watch_dirs": [],
        "always_recent": 3
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