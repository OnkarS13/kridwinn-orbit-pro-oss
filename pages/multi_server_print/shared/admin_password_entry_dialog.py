"""
Admin Password Entry Dialog
Authentication dialog for admin panel access
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QCheckBox
)


class AdminPasswordEntryDialog(QDialog):
    """Dialog for admin password authentication"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.password = ""
        self.attempt_count = 0
        self.max_attempts = 5
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components"""
        self.setWindowTitle("Admin Authentication")
        self.setModal(True)
        self.setMinimumSize(420, 260)
        self.resize(420, 260)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Header
        header = QLabel("Admin Authentication")
        header.setStyleSheet("font-size: 14pt; font-weight: bold; color: #212529;")
        layout.addWidget(header)
        
        # Instructions
        instructions = QLabel("Enter admin password to access settings:")
        instructions.setStyleSheet("color: #6c757d; font-size: 10pt;")
        layout.addWidget(instructions)
        
        layout.addSpacing(5)
        
        # Password input with show/hide toggle
        pwd_row = QHBoxLayout()
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter password...")
        self.password_input.setMinimumHeight(35)
        self.password_input.returnPressed.connect(self._on_login)
        pwd_row.addWidget(self.password_input)
        
        # Show/Hide password toggle with SVG icons
        from pathlib import Path
        from PySide6.QtGui import QIcon
        
        assets_dir = Path(__file__).parent / "assets"
        self.eye_hide_icon = QIcon(str(assets_dir / "eye-hide.svg"))
        self.eye_show_icon = QIcon(str(assets_dir / "eye-show.svg"))
        
        self.show_password_btn = QPushButton()
        self.show_password_btn.setIcon(self.eye_hide_icon)
        self.show_password_btn.setFixedSize(40, 35)
        self.show_password_btn.setCheckable(True)
        self.show_password_btn.setToolTip("Show/Hide password")
        self.show_password_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e9ecef;
            }
            QPushButton:checked {
                background-color: #dee2e6;
            }
        """)
        self.show_password_btn.toggled.connect(self._toggle_password_visibility)
        pwd_row.addWidget(self.show_password_btn)
        
        layout.addLayout(pwd_row)
        
        # Error message
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #dc3545; font-size: 9pt;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.login_btn = QPushButton("Login")
        self.login_btn.setMinimumHeight(35)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.login_btn.clicked.connect(self._on_login)
        button_layout.addWidget(self.login_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(35)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Help text
        help_text = QLabel("Forgot password? Contact system administrator")
        help_text.setStyleSheet("color: #6c757d; font-size: 8pt; font-style: italic;")
        help_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(help_text)
        
        # Set focus to password input
        self.password_input.setFocus()
    
    def _toggle_password_visibility(self, checked):
        """Toggle password visibility"""
        if checked:
            self.password_input.setEchoMode(QLineEdit.Normal)
            self.show_password_btn.setIcon(self.eye_show_icon)
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            self.show_password_btn.setIcon(self.eye_hide_icon)
    
    def _on_login(self):
        """Handle login button click"""
        password = self.password_input.text()
        
        if not password:
            self.error_label.setText("Please enter password")
            return
        
        # Store password and accept
        # Actual verification will be done by the caller
        self.password = password
        self.accept()
    
    def show_error(self, message: str):
        """
        Show error message
        
        Args:
            message: Error message to display
        """
        self.error_label.setText(message)
        self.password_input.clear()
        self.password_input.setFocus()
        
        # Track attempts
        self.attempt_count += 1
        if self.attempt_count >= 3:
            self.error_label.setText(
                f"{message}\n"
                f"Warning: {self.attempt_count} failed attempts"
            )
    
    def get_password(self) -> str:
        """Get the entered password"""
        return self.password
