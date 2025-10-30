"""
Onboarding dialog for first-time users of Ghost Widget
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import winreg
import sys
import os


class OnboardingDialog(QDialog):
    """
    Simple onboarding dialog shown to first-time users
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_on_boot_enabled = False
        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("Welcome to Ghost Widget")
        self.setModal(True)
        self.setFixedSize(500, 400)

        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

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
        subtitle.setStyleSheet("color: #666; font-size: 12pt;")
        layout.addWidget(subtitle)

        layout.addSpacing(20)

        # Features section
        features = QLabel(
            "Ghost Widget helps you:\n\n"
            "• Record and analyze your screen automatically\n"
            "• Answer questions about your work context\n"
            "• Keep track of your activity with smart AI\n"
            "• Access your companion with Ctrl+Alt+` hotkey"
        )
        features.setStyleSheet("font-size: 11pt; line-height: 1.6;")
        features.setWordWrap(True)
        layout.addWidget(features)

        layout.addSpacing(20)

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
            "This allows Ghost Widget to run in the background and\n"
            "capture context automatically. You can change this later\n"
            "in Settings."
        )
        boot_description.setStyleSheet("color: #666; font-size: 9pt; margin-left: 25px;")
        boot_layout.addWidget(boot_description)

        layout.addWidget(boot_section)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.get_started_btn = QPushButton("Get Started")
        self.get_started_btn.setStyleSheet("""
            QPushButton {
                background-color: #4285f4;
                color: white;
                border: none;
                padding: 10px 30px;
                font-size: 11pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #357ae8;
            }
            QPushButton:pressed {
                background-color: #2a5db0;
            }
        """)
        self.get_started_btn.clicked.connect(self.on_get_started)
        button_layout.addWidget(self.get_started_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

        # Center on screen
        self.center_on_screen()

    def center_on_screen(self):
        """Center the dialog on the screen"""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def on_get_started(self):
        """Handle Get Started button click"""
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
