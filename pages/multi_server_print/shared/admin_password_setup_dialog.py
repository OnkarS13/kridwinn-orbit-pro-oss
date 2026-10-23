"""
Admin Password Setup Dialog
First-time password setup for admin panel access
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QMessageBox
)


class AdminPasswordSetupDialog(QDialog):
    """Dialog for first-time admin password setup"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.password = ""
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components"""
        self.setWindowTitle("Set Up Admin Password")
        self.setModal(True)
        self.setMinimumSize(440, 340)
        self.resize(440, 340)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Header
        header = QLabel("Create Admin Password")
        header.setStyleSheet("font-size: 16pt; font-weight: bold; color: #212529;")
        layout.addWidget(header)
        
        # Instructions
        instructions = QLabel(
            "Create a password to protect admin settings.\n"
            "Password must be 8-10 characters long."
        )
        instructions.setStyleSheet("color: #6c757d; font-size: 10pt;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        layout.addSpacing(10)
        
        # Password input
        pwd_label = QLabel("Password:")
        pwd_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(pwd_label)
        
        pwd_row = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter password...")
        self.password_input.setMinimumHeight(35)
        self.password_input.textChanged.connect(self._on_password_changed)
        pwd_row.addWidget(self.password_input)
        
        self.char_count_label = QLabel("0/10")
        self.char_count_label.setStyleSheet("color: #6c757d; font-size: 9pt;")
        self.char_count_label.setFixedWidth(50)
        pwd_row.addWidget(self.char_count_label)
        
        layout.addLayout(pwd_row)
        
        # Confirm password input
        confirm_label = QLabel("Confirm Password:")
        confirm_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(confirm_label)
        
        confirm_row = QHBoxLayout()
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText("Re-enter password...")
        self.confirm_input.setMinimumHeight(35)
        self.confirm_input.textChanged.connect(self._on_confirm_changed)
        confirm_row.addWidget(self.confirm_input)
        
        self.match_label = QLabel("")
        self.match_label.setFixedWidth(50)
        confirm_row.addWidget(self.match_label)
        
        layout.addLayout(confirm_row)
        
        # Validation message
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet("color: #dc3545; font-size: 9pt;")
        self.validation_label.setWordWrap(True)
        layout.addWidget(self.validation_label)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.setup_btn = QPushButton("Setup")
        self.setup_btn.setMinimumHeight(35)
        self.setup_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.setup_btn.setEnabled(False)
        self.setup_btn.clicked.connect(self._on_setup)
        button_layout.addWidget(self.setup_btn)
        
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
        
        # Set focus to password input
        self.password_input.setFocus()
    
    def _on_password_changed(self):
        """Handle password input change"""
        password = self.password_input.text()
        length = len(password)
        
        # Update character count
        self.char_count_label.setText(f"{length}/10")
        
        # Update character count color
        if length < 8:
            self.char_count_label.setStyleSheet("color: #dc3545; font-size: 9pt;")
        elif length <= 10:
            self.char_count_label.setStyleSheet("color: #28a745; font-size: 9pt;")
        else:
            self.char_count_label.setStyleSheet("color: #dc3545; font-size: 9pt;")
        
        self._validate()
    
    def _on_confirm_changed(self):
        """Handle confirm password input change"""
        self._validate()
    
    def _validate(self):
        """Validate password inputs and update UI"""
        password = self.password_input.text()
        confirm = self.confirm_input.text()
        length = len(password)
        
        # Clear previous validation
        self.validation_label.setText("")
        self.match_label.setText("")
        self.setup_btn.setEnabled(False)
        
        # Check length
        if length > 0 and (length < 8 or length > 10):
            self.validation_label.setText("Password must be 8-10 characters")
            return
        
        # Check if passwords match
        if confirm:
            if password == confirm:
                self.match_label.setText("✓")
                self.match_label.setStyleSheet("color: #28a745; font-size: 12pt; font-weight: bold;")
                
                # Enable setup button if length is valid
                if 8 <= length <= 10:
                    self.setup_btn.setEnabled(True)
            else:
                self.match_label.setText("✗")
                self.match_label.setStyleSheet("color: #dc3545; font-size: 12pt; font-weight: bold;")
                self.validation_label.setText("Passwords do not match")
    
    def _on_setup(self):
        """Handle setup button click"""
        password = self.password_input.text()
        
        # Final validation
        if not (8 <= len(password) <= 10):
            QMessageBox.warning(
                self,
                "Invalid Password",
                "Password must be 8-10 characters long."
            )
            return
        
        if password != self.confirm_input.text():
            QMessageBox.warning(
                self,
                "Password Mismatch",
                "Passwords do not match."
            )
            return
        
        # Store password and accept
        self.password = password
        self.accept()
    
    def get_password(self) -> str:
        """Get the entered password"""
        return self.password
