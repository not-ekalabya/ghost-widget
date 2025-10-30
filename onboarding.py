"""
Onboarding dialog for first-time users of Ghost Widget
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QWidget, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
import winreg
import sys
import os
import threading
import time
from queue import Queue, Empty


class OnboardingDialog(QDialog):
    """
    Onboarding dialog shown to first-time users
    Requires Google and GitHub authentication before proceeding
    """

    auth_complete = pyqtSignal()

    def __init__(self, firebase_auth=None, github_auth=None, parent=None):
        super().__init__(parent)
        self.firebase_auth = firebase_auth
        self.github_auth = github_auth
        self.start_on_boot_enabled = False
        self.google_authenticated = False
        self.github_authenticated = False
        self.github_username = None
        self._auth_queue = Queue()
        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("Welcome to Ghost Widget")
        self.setModal(True)
        self.setFixedSize(600, 650)

        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(30, 25, 30, 25)

        # Title
        title = QLabel("Welcome to Ghost Widget!")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Your AI-powered screen recording companion")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #666; font-size: 10pt;")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Features section
        features = QLabel(
            "Ghost Widget helps you:\n"
            "• Record and analyze your screen automatically\n"
            "• Answer questions about your work context\n"
            "• Integrate with GitHub for code context\n"
            "• Access your companion with Ctrl+Alt+` hotkey"
        )
        features.setStyleSheet("font-size: 10pt; line-height: 1.4;")
        features.setWordWrap(True)
        layout.addWidget(features)

        layout.addSpacing(12)

        # Authentication section
        auth_section = QWidget()
        auth_layout = QVBoxLayout(auth_section)
        auth_layout.setContentsMargins(0, 0, 0, 0)
        auth_layout.setSpacing(8)

        # Section header
        auth_header = QLabel("Required Setup")
        auth_header_font = QFont()
        auth_header_font.setBold(True)
        auth_header_font.setPointSize(11)
        auth_header.setFont(auth_header_font)
        auth_layout.addWidget(auth_header)

        auth_layout.addSpacing(5)

        # Google Sign-In
        google_label = QLabel("1. Sign in with Google (Required)")
        google_label.setStyleSheet("font-weight: 600; font-size: 9.5pt; margin-top: 5px;")
        auth_layout.addWidget(google_label)

        self.google_signin_btn = QPushButton("🔐 Sign in with Google")
        self.google_signin_btn.setStyleSheet("""
            QPushButton {
                background-color: #4285f4;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 9.5pt;
                border-radius: 5px;
                text-align: left;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #357ae8;
            }
            QPushButton:pressed {
                background-color: #2a5db0;
            }
            QPushButton:disabled {
                background-color: #10B981;
            }
        """)
        self.google_signin_btn.clicked.connect(self.on_google_signin)
        auth_layout.addWidget(self.google_signin_btn)

        self.google_status_label = QLabel("")
        self.google_status_label.setStyleSheet("color: #666; font-size: 8.5pt; margin-left: 5px; margin-top: 3px;")
        self.google_status_label.setWordWrap(True)
        auth_layout.addWidget(self.google_status_label)

        auth_layout.addSpacing(8)

        # GitHub Sign-In
        github_label = QLabel("2. Connect GitHub (Optional)")
        github_label.setStyleSheet("font-weight: 600; font-size: 9.5pt; margin-top: 5px;")
        auth_layout.addWidget(github_label)

        self.github_signin_btn = QPushButton("🔗 Connect GitHub")
        self.github_signin_btn.setStyleSheet("""
            QPushButton {
                background-color: #24292e;
                color: white;
                border: none;
                padding: 8px 16px;
                font-size: 9.5pt;
                border-radius: 5px;
                text-align: left;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #1b1f23;
            }
            QPushButton:pressed {
                background-color: #0d1117;
            }
            QPushButton:disabled {
                background-color: #10B981;
            }
        """)
        self.github_signin_btn.setEnabled(False)  # Disabled until Google sign-in
        self.github_signin_btn.clicked.connect(self.on_github_signin)
        auth_layout.addWidget(self.github_signin_btn)

        self.github_status_label = QLabel("Complete Google sign-in first")
        self.github_status_label.setStyleSheet("color: #999; font-size: 8.5pt; margin-left: 5px; margin-top: 3px;")
        self.github_status_label.setWordWrap(True)
        auth_layout.addWidget(self.github_status_label)

        # Add a large, prominent label for the GitHub user code (hidden by default)
        self.github_code_label = QLabel("")
        self.github_code_label.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a;
                color: #4CAF50;
                font-size: 20pt;
                font-weight: bold;
                font-family: 'Courier New', monospace;
                letter-spacing: 4px;
                padding: 15px;
                border: 2px solid #4CAF50;
                border-radius: 8px;
                qproperty-alignment: AlignCenter;
            }
        """)
        self.github_code_label.setVisible(False)
        self.github_code_label.setWordWrap(True)
        auth_layout.addWidget(self.github_code_label)

        layout.addWidget(auth_section)

        layout.addSpacing(12)

        # Start on boot section
        boot_section = QWidget()
        boot_layout = QVBoxLayout(boot_section)
        boot_layout.setContentsMargins(0, 0, 0, 0)

        boot_label = QLabel("Background Mode")
        boot_label_font = QFont()
        boot_label_font.setBold(True)
        boot_label_font.setPointSize(11)
        boot_label.setFont(boot_label_font)
        boot_layout.addWidget(boot_label)

        self.start_on_boot_checkbox = QCheckBox(
            "Start Ghost Widget when Windows starts (recommended)"
        )
        self.start_on_boot_checkbox.setStyleSheet("font-size: 10pt;")
        self.start_on_boot_checkbox.setChecked(True)
        boot_layout.addWidget(self.start_on_boot_checkbox)

        boot_description = QLabel(
            "Ghost Widget will run in the background and capture context automatically. You can change this in Settings."
        )
        boot_description.setStyleSheet("color: #666; font-size: 8.5pt; margin-left: 25px;")
        boot_description.setWordWrap(True)
        boot_layout.addWidget(boot_description)

        layout.addWidget(boot_section)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.get_started_btn = QPushButton("Complete Setup")
        self.get_started_btn.setStyleSheet("""
            QPushButton {
                background-color: #4285f4;
                color: white;
                border: none;
                padding: 10px 30px;
                font-size: 10.5pt;
                font-weight: bold;
                border-radius: 5px;
                min-height: 40px;
            }
            QPushButton:hover {
                background-color: #357ae8;
            }
            QPushButton:pressed {
                background-color: #2a5db0;
            }
            QPushButton:disabled {
                background-color: #ccc;
                color: #666;
            }
        """)
        self.get_started_btn.setEnabled(False)  # Disabled until Google auth completes
        self.get_started_btn.clicked.connect(self.on_get_started)
        button_layout.addWidget(self.get_started_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Center on screen
        self.center_on_screen()

        # Start polling for auth results
        self.start_auth_polling()

    def center_on_screen(self):
        """Center the dialog on the screen"""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def start_auth_polling(self):
        """Start polling for authentication results"""
        from PyQt6.QtCore import QTimer
        self.auth_timer = QTimer()
        self.auth_timer.timeout.connect(self.poll_auth_queue)
        self.auth_timer.start(100)  # Poll every 100ms

    def poll_auth_queue(self):
        """Poll the auth queue for results from background threads"""
        try:
            while not self._auth_queue.empty():
                msg_type, data = self._auth_queue.get_nowait()

                if msg_type == "GOOGLE_AUTH_RESULT":
                    self.handle_google_auth_result(data)
                elif msg_type == "GITHUB_AUTH_RESULT":
                    self.handle_github_auth_result(data)
                elif msg_type == "GITHUB_PROGRESS":
                    self.github_status_label.setText(data)
                elif msg_type == "GITHUB_USER_CODE":
                    # Display user code prominently in the UI
                    user_code = data.get('user_code', '')
                    verification_url = data.get('verification_url', 'https://github.com/login/device')

                    print(f"[ONBOARDING] Displaying GitHub user code: {user_code}")

                    # Show the large code label
                    self.github_code_label.setText(f"ENTER CODE:\n{user_code}")
                    self.github_code_label.setVisible(True)

                    # Update status label
                    self.github_status_label.setText(f"Browser opened. Enter the code above on GitHub.")
                    self.github_status_label.setStyleSheet("color: #4CAF50; font-size: 9pt; margin-left: 5px; font-weight: bold;")
        except Empty:
            pass

    def on_google_signin(self):
        """Handle Google Sign-In"""
        if not self.firebase_auth:
            QMessageBox.critical(
                self,
                "Error",
                "Firebase Auth not configured. Please contact support."
            )
            return

        self.google_signin_btn.setEnabled(False)
        self.google_signin_btn.setText("Signing in...")
        self.google_status_label.setText("Opening browser...")

        def sign_in_thread():
            result = self.firebase_auth.sign_in_with_google()
            self._auth_queue.put(("GOOGLE_AUTH_RESULT", result))

        threading.Thread(target=sign_in_thread, daemon=True).start()

    def handle_google_auth_result(self, result):
        """Handle Google authentication result"""
        if result['success']:
            self.google_authenticated = True
            self.google_signin_btn.setEnabled(False)
            self.google_signin_btn.setText("✓ Signed In")
            user = result.get('user', {})
            email = user.get('email', 'Google Account')
            self.google_status_label.setText(f"Authenticated as {email}")
            self.google_status_label.setStyleSheet("color: #10B981; font-size: 8.5pt; margin-left: 5px; margin-top: 3px;")

            # Enable GitHub sign-in
            self.github_signin_btn.setEnabled(True)
            self.github_status_label.setText("Optional: You can connect GitHub now or skip")
            self.github_status_label.setStyleSheet("color: #666; font-size: 8.5pt; margin-left: 5px; margin-top: 3px;")

            # Enable the Complete Setup button - user can proceed without GitHub
            self.get_started_btn.setEnabled(True)
        else:
            self.google_signin_btn.setEnabled(True)
            self.google_signin_btn.setText("🔐 Sign in with Google")
            self.google_status_label.setText(f"Error: {result.get('message', 'Unknown error')}")
            self.google_status_label.setStyleSheet("color: #EF4444; font-size: 8.5pt; margin-left: 5px; margin-top: 3px;")

    def on_github_signin(self):
        """Handle GitHub Sign-In"""
        if not self.github_auth:
            QMessageBox.critical(
                self,
                "Error",
                "GitHub Auth not configured. Please contact support."
            )
            return

        self.github_signin_btn.setEnabled(False)
        self.github_signin_btn.setText("Connecting...")
        self.github_status_label.setText("Opening browser...")

        def sign_in_thread():
            def progress_callback(message, user_code=None, verification_url=None):
                # If this is the user code message, send it separately
                if user_code:
                    self._auth_queue.put(("GITHUB_USER_CODE", {
                        'user_code': user_code,
                        'verification_url': verification_url
                    }))
                else:
                    self._auth_queue.put(("GITHUB_PROGRESS", message))

            result = self.github_auth.sign_in_with_browser(progress_callback=progress_callback)
            self._auth_queue.put(("GITHUB_AUTH_RESULT", result))

        threading.Thread(target=sign_in_thread, daemon=True).start()

    def handle_github_auth_result(self, result):
        """Handle GitHub authentication result"""
        if result['success']:
            self.github_authenticated = True
            self.github_username = result.get('user')
            self.github_signin_btn.setEnabled(False)
            self.github_signin_btn.setText("✓ Connected")

            # Hide the code label
            self.github_code_label.setVisible(False)

            self.github_status_label.setText(f"Connected as {self.github_username}")
            self.github_status_label.setStyleSheet("color: #10B981; font-size: 8.5pt; margin-left: 5px; margin-top: 3px;")
        else:
            self.github_signin_btn.setEnabled(True)
            self.github_signin_btn.setText("🔗 Connect GitHub")

            # Hide the code label on error
            self.github_code_label.setVisible(False)

            error_msg = result.get('message', 'Unknown error')
            self.github_status_label.setText(f"Error: {error_msg}. You can proceed without GitHub.")
            self.github_status_label.setStyleSheet("color: #EF4444; font-size: 8.5pt; margin-left: 5px; margin-top: 3px;")

    def on_get_started(self):
        """Handle Get Started button click"""
        # Only require Google authentication
        if not self.google_authenticated:
            QMessageBox.warning(
                self,
                "Setup Incomplete",
                "Please complete Google authentication before continuing."
            )
            return

        self.start_on_boot_enabled = self.start_on_boot_checkbox.isChecked()

        if self.start_on_boot_enabled:
            self.enable_start_on_boot()

        self.accept()

    def enable_start_on_boot(self):
        """Add Ghost Widget to Windows startup"""
        try:
            # Get the path to the executable
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                app_path = sys.executable
            else:
                # Running as script
                app_path = os.path.abspath(sys.argv[0])

            # Add to Windows registry
            key = winreg.HKEY_CURRENT_USER
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

            registry_key = winreg.OpenKey(key, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(registry_key, "GhostWidget", 0, winreg.REG_SZ, f'"{app_path}"')
            winreg.CloseKey(registry_key)

            print("[OK] Ghost Widget added to startup")
            return True

        except Exception as e:
            print(f"[WARNING] Failed to add to startup: {e}")
            return False

    @staticmethod
    def disable_start_on_boot():
        """Remove Ghost Widget from Windows startup"""
        try:
            key = winreg.HKEY_CURRENT_USER
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

            registry_key = winreg.OpenKey(key, key_path, 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(registry_key, "GhostWidget")
                print("[OK] Ghost Widget removed from startup")
            except FileNotFoundError:
                pass  # Already not in startup
            winreg.CloseKey(registry_key)

            return True

        except Exception as e:
            print(f"[WARNING] Failed to remove from startup: {e}")
            return False

    @staticmethod
    def is_start_on_boot_enabled():
        """Check if Ghost Widget is set to start on boot"""
        try:
            key = winreg.HKEY_CURRENT_USER
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

            registry_key = winreg.OpenKey(key, key_path, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(registry_key, "GhostWidget")
                winreg.CloseKey(registry_key)
                return True
            except FileNotFoundError:
                winreg.CloseKey(registry_key)
                return False

        except Exception as e:
            print(f"[WARNING] Failed to check startup status: {e}")
            return False
