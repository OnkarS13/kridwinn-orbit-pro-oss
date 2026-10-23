from typing import Optional, Dict, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QLinearGradient, QColor, QPainter, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QSizePolicy,
)

# Import licensing components
try:
    from pages.licensing.license_client import LicenseClient
    from pages.licensing.activation_dialog import ActivationDialog
    LICENSING_AVAILABLE = True
except ImportError:
    LICENSING_AVAILABLE = False


class LoginDialog(QDialog):
    """
    Login dialog with integrated licensing system.
    Checks license before allowing login.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Kridwinn Orbit Pro – Sign In")
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        
        # Set reasonable size constraints
        self.setMinimumSize(900, 600)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Initialize licensing
        self.license_client = None
        self.license_valid = False

        if LICENSING_AVAILABLE:
            try:
                self.licensing_enabled = True
                self.license_client = LicenseClient()
            except Exception as e:
                import logging
                logging.error(f"Failed to initialize licensing: {e}")
                self.licensing_enabled = False
        else:
            self.licensing_enabled = False

        # Root layout split into left (branding) and right (form)
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Left branded panel
        left_panel = GradientWidget()
        left_panel.setMinimumWidth(320)
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(60, 60, 60, 60)
        left_layout.setSpacing(20)

        left_layout.addStretch(2)

        welcome_label = QLabel("Welcome\nBack!")
        welcome_label.setStyleSheet(
            """
            color: white;
            font-size: 48px;
            font-weight: bold;
            line-height: 1.15;
            """
        )
        welcome_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        left_layout.addWidget(welcome_label)
        left_layout.addStretch(3)

        # Right login form panel
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #f5f5f5;")
        right_panel.setMinimumWidth(380)
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        form_layout = QVBoxLayout(right_panel)
        form_layout.setContentsMargins(70, 50, 70, 50)
        form_layout.setSpacing(28)
        
        # Add spacing to push title and subtitle down
        form_layout.addSpacing(160)

        title_label = QLabel("Login")
        title_label.setStyleSheet(
            """
            color: #333333;
            font-size: 36px;
            font-weight: bold;
            """
        )
        title_label.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        subtitle_label = QLabel("Welcome back! Please login to your account.")
        subtitle_label.setStyleSheet(
            """
            color: #6b7280;
            font-size: 15px;
            """
        )
        subtitle_label.setWordWrap(True)
        subtitle_label.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        form_layout.addWidget(title_label)
        form_layout.addWidget(subtitle_label)
        form_layout.addSpacing(20)

        # Add stretch at top to push form elements to center
        form_layout.addStretch(1)

        username_label = QLabel("User Name")
        username_label.setStyleSheet("color: #4b5563; font-size: 14px; font-weight: 600; letter-spacing: 0.5px;")
        form_layout.addWidget(username_label)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Enter your username")
        self.email_edit.setClearButtonEnabled(True)
        self.email_edit.setStyleSheet(
            """
            QLineEdit {
                padding: 12px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background-color: white;
                color: #000000;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #7c3aed;
            }
            """
        )
        form_layout.addWidget(self.email_edit)
        form_layout.addSpacing(10)

        password_label = QLabel("Password")
        password_label.setStyleSheet("color: #4b5563; font-size: 14px; font-weight: 600; letter-spacing: 0.5px;")
        form_layout.addWidget(password_label)

        # Password field with show/hide button
        password_container = QHBoxLayout()
        password_container.setSpacing(12)
        
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("••••••••")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setClearButtonEnabled(True)
        self.password_edit.setStyleSheet(
            """
            QLineEdit {
                padding: 12px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background-color: white;
                color: #000000;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #7c3aed;
            }
            """
        )
        password_container.addWidget(self.password_edit)
        
        # Show/Hide password button
        self.show_password_btn = QPushButton("Show")
        self.show_password_btn.setFixedSize(60, 40)
        self.show_password_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                font-size: 13px;
                color: #111827;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                color: #111827;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
                color: #111827;
            }
            """
        )
        self.show_password_btn.clicked.connect(self._toggle_password_visibility)
        password_container.addWidget(self.show_password_btn)
        
        form_layout.addLayout(password_container)
        form_layout.addSpacing(12)

        links_layout = QHBoxLayout()
        links_layout.addStretch(1)
        self.forgot_button = QPushButton("Forgot Password?")
        self.forgot_button.setCursor(Qt.PointingHandCursor)
        self.forgot_button.setStyleSheet(
            """
            QPushButton {
                color: #7c3aed;
                background: transparent;
                border: none;
                font-size: 13px;
                text-decoration: underline;
            }
            QPushButton:hover {
                color: #6d28d9;
            }
            """
        )
        self.forgot_button.clicked.connect(self._handle_forgot_password)
        links_layout.addWidget(self.forgot_button)
        form_layout.addLayout(links_layout)

        self.login_button = QPushButton("Login")
        self.login_button.setDefault(True)
        # Login button is always enabled - license check happens on click
        self.login_button.setStyleSheet(
            """
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 20px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
            QPushButton:pressed {
                background-color: #5b21b6;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
            """
        )
        self.login_button.setMinimumHeight(56)
        form_layout.addWidget(self.login_button)
        form_layout.addSpacing(20)
        form_layout.addStretch(2)

        # "Get License Key" and "Manage License" buttons (only visible if activated) - positioned at bottom center
        if self.licensing_enabled and self.license_client:
            license_key_layout = QHBoxLayout()
            license_key_layout.addStretch(1)
            
            # "Get License Key" button
            self.license_key_button = QPushButton("Get License Key")
            self.license_key_button.setStyleSheet(
                """
                QPushButton {
                    background-color: transparent;
                    color: #7c3aed;
                    border: 1px solid #7c3aed;
                    border-radius: 5px;
                    padding: 10px 20px;
                    font-size: 14px;
                    font-weight: 500;
                    min-width: 140px;
                }
                QPushButton:hover {
                    background-color: #f3f4f6;
                    color: #6d28d9;
                    border-color: #6d28d9;
                }
                QPushButton:pressed {
                    background-color: #e5e7eb;
                    color: #5b21b6;
                }
                """
            )
            self.license_key_button.clicked.connect(self._show_license_info)
            # Initially hidden, will be shown if activated
            self.license_key_button.setVisible(False)
            license_key_layout.addWidget(self.license_key_button)
            
            # Add spacing between buttons
            license_key_layout.addSpacing(10)
            
            # "Manage License" button (same style as Get License Key)
            self.manage_license_button = QPushButton("Manage License")
            self.manage_license_button.setStyleSheet(
                """
                QPushButton {
                    background-color: transparent;
                    color: #7c3aed;
                    border: 1px solid #7c3aed;
                    border-radius: 5px;
                    padding: 10px 20px;
                    font-size: 14px;
                    font-weight: 500;
                    min-width: 140px;
                }
                QPushButton:hover {
                    background-color: #f3f4f6;
                    color: #6d28d9;
                    border-color: #6d28d9;
                }
                QPushButton:pressed {
                    background-color: #e5e7eb;
                    color: #5b21b6;
                }
                """
            )
            self.manage_license_button.clicked.connect(self._show_license_info_dialog)
            # Initially hidden, will be shown if activated
            self.manage_license_button.setVisible(False)
            license_key_layout.addWidget(self.manage_license_button)
            
            license_key_layout.addStretch(1)
            form_layout.addLayout(license_key_layout)
            form_layout.addSpacing(10)

        # License status indicator (if licensing enabled) bottom-right
        if self.licensing_enabled and self.license_client:
            license_status_layout = QHBoxLayout()
            license_status_layout.addStretch(1)
            esc_hint = QLabel("Press Esc to exit")
            esc_hint.setStyleSheet("color: #94a3b8; font-size: 12px; margin-right: 12px;")
            license_status_layout.addWidget(esc_hint)
            self.license_status_text = QLabel("Ready to login")
            self.license_status_text.setStyleSheet(
                "font-size: 18px; color: #6b7280; font-weight: 700; letter-spacing: 0.4px;"
            )
            license_status_layout.addWidget(self.license_status_text)
            form_layout.addLayout(license_status_layout)

        # removed signup prompt per request

        # Assemble panels with adaptive proportions (60% left, 40% right)
        self.setLayout(root_layout)
        root_layout.addWidget(left_panel, stretch=6)
        root_layout.addWidget(right_panel, stretch=4)
        root_layout.setStretch(0, 6)
        root_layout.setStretch(1, 4)

        self.login_button.clicked.connect(self._on_login_clicked)

        # Apply base font
        self.setFont(QFont("Segoe UI", 10))
        self._apply_responsive_layout()
        
        # Ensure activation state on startup (but do not validate yet)
        if self.licensing_enabled and self.license_client:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(300, self._ensure_activation_ready)

        # Set dialog background for clarity
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f5f5f5;
            }
            """
        )

    def get_credentials(self) -> tuple[str, str]:
        """Return the entered credentials (username, password)."""
        return (
            self.email_edit.text().strip(),
            self.password_edit.text(),
        )
    
    def _ensure_activation_ready(self):
        """Ensure license is activated on startup (no validation)"""
        if not self.license_client:
            return
        
        if not self.license_client.is_activated():
            self._update_license_status("Activation required", "#dc3545")
            
            activation_dialog = ActivationDialog(self.license_client, self)
            if activation_dialog.exec() == QDialog.Accepted:
                self._update_license_status("Ready to login", "#6b7280")
                # Show license key button after activation
                if hasattr(self, 'license_key_button'):
                    self.license_key_button.setVisible(True)
                # Show manage license button after activation
                if hasattr(self, 'manage_license_button'):
                    self.manage_license_button.setVisible(True)
            else:
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.setWindowTitle("Activation Required")
                msg_box.setText("This application cannot run without activation. The program will now exit.")
                msg_box.setStyleSheet("""
                    QMessageBox {
                        background-color: white;
                    }
                    QLabel {
                        color: #000000;
                        font-size: 13px;
                    }
                    QPushButton {
                        background-color: #7c3aed;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 8px 16px;
                        font-size: 13px;
                        min-width: 80px;
                    }
                    QPushButton:hover {
                        background-color: #6d28d9;
                    }
                """)
                msg_box.exec()
                import sys
                sys.exit(0)
        else:
            # Already activated, show the buttons
            if hasattr(self, 'license_key_button'):
                self.license_key_button.setVisible(True)
            if hasattr(self, 'manage_license_button'):
                self.manage_license_button.setVisible(True)
    
    def _show_expired_dialog(self):
        """Show dialog when trial license has expired"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Trial Period Ended")
        msg_box.setText(
            "Your trial period has ended.\n\n"
            "Please contact your administrator for a new license file."
        )
        msg_box.setStyleSheet("""
            QMessageBox { background-color: white; }
            QLabel { color: #1f2937; font-size: 13px; }
            QPushButton {
                background-color: #7c3aed; color: white; border: none;
                border-radius: 4px; padding: 8px 16px; font-size: 13px; min-width: 100px;
            }
            QPushButton:hover { background-color: #6d28d9; }
        """)
        reimport_btn = msg_box.addButton("Import New License", QMessageBox.AcceptRole)
        exit_btn = msg_box.addButton("Close", QMessageBox.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == reimport_btn:
            # Deactivate old license and show activation dialog
            self.license_client.deactivate()
            activation_dialog = ActivationDialog(self.license_client, self)
            activation_dialog.exec()
            
    
    def _update_license_status(self, text: str, color: str):
        """Update license status indicator"""
        if hasattr(self, 'license_status_text'):
            self.license_status_text.setText(text)
            self.license_status_text.setStyleSheet(
                f"font-size: 18px; font-weight: 700; letter-spacing: 0.4px; color: {color};"
            )
    
    def _toggle_password_visibility(self):
        """Toggle password visibility"""
        if self.password_edit.echoMode() == QLineEdit.Password:
            self.password_edit.setEchoMode(QLineEdit.Normal)
            self.show_password_btn.setText("Hide")
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.show_password_btn.setText("Show")
    
    def _handle_forgot_password(self):
        """Display forgot password instructions"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("Need help?")
        msg_box.setText(
            "Please contact your administrator to reset your password.\n\n"
            "They can generate new credentials for you via the licensing portal."
        )
        msg_box.setStyleSheet(
            """
            QMessageBox {
                background-color: white;
            }
            QLabel {
                color: #1f2937;
                font-size: 13px;
            }
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
            """
        )
        msg_box.exec()
    
    def _show_trial_reminder(self, trial_info: Dict[str, Any]):
        """Show trial reminder popup after successful login"""
        days_remaining = trial_info.get('days_remaining', 0)
        expires_at_str = trial_info.get('expires_at_str', 'N/A')
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("⏰ Trial Version")
        msg_box.setText(
            f"You are using the trial version.\n\n"
            f"Days Remaining: {days_remaining} day{'s' if days_remaining != 1 else ''}\n"
            f"Expires: {expires_at_str}\n\n"
            f"Purchase full license to continue using after trial."
        )
        msg_box.setStyleSheet(
            """
            QMessageBox {
                background-color: white;
            }
            QLabel {
                color: #1f2937;
                font-size: 13px;
            }
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
            """
        )
        msg_box.exec()
    
    def _show_license_info(self):
        """Show license information dialog with copy functionality"""
        if not self.license_client or not self.license_client.is_activated():
            return
        
        # Get license information
        license_info = self.license_client.get_license_info()
        license_id = license_info.get('license_id', license_info.get('license_key', 'N/A'))
        machine_id = license_info.get('machine_id', 'N/A')

        # Create custom dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Your License Information")
        dialog.setMinimumWidth(500)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: white;
            }
            QLabel {
                color: #1f2937;
                font-size: 13px;
            }
            QLineEdit {
                padding: 10px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background-color: #f9fafb;
                color: #111827;
                font-size: 13px;
                font-family: 'Courier New', monospace;
            }
            QLineEdit:focus {
                border: 1px solid #7c3aed;
            }
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 500;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
            QPushButton:pressed {
                background-color: #5b21b6;
            }
            """
        )
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title_label = QLabel("Your License Information")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #111827; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # License ID section
        license_label = QLabel("License ID:")
        license_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #4b5563; margin-top: 10px;")
        layout.addWidget(license_label)

        license_key_layout = QHBoxLayout()
        license_key_input = QLineEdit(license_id)
        license_key_input.setReadOnly(True)
        license_key_input.setStyleSheet(
            """
            QLineEdit {
                padding: 10px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background-color: #f9fafb;
                color: #111827;
                font-size: 13px;
                font-family: 'Courier New', monospace;
            }
            """
        )
        license_key_layout.addWidget(license_key_input)

        copy_button = QPushButton("Copy")
        copy_button.setFixedWidth(100)
        copy_button.clicked.connect(lambda: self._copy_to_clipboard(license_id, copy_button))
        license_key_layout.addWidget(copy_button)
        layout.addLayout(license_key_layout)
        
        # Machine ID section
        machine_label = QLabel("Machine ID:")
        machine_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #4b5563; margin-top: 10px;")
        layout.addWidget(machine_label)
        
        machine_id_input = QLineEdit(machine_id)
        machine_id_input.setReadOnly(True)
        machine_id_input.setStyleSheet(
            """
            QLineEdit {
                padding: 10px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background-color: #f9fafb;
                color: #111827;
                font-size: 13px;
                font-family: 'Courier New', monospace;
            }
            """
        )
        layout.addWidget(machine_id_input)
        
        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        
        dialog.exec()
    
    def _copy_to_clipboard(self, text: str, button: QPushButton):
        """Copy text to clipboard and show success feedback"""
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)
        
        # Show success feedback
        original_text = button.text()
        button.setText("✓ Copied!")
        button.setStyleSheet(
            """
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 500;
                min-width: 100px;
            }
            """
        )
        
        # Reset after 2 seconds
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: (
            button.setText(original_text),
            button.setStyleSheet(
                """
                QPushButton {
                    background-color: #7c3aed;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                    min-width: 100px;
                }
                QPushButton:hover {
                    background-color: #6d28d9;
                }
                QPushButton:pressed {
                    background-color: #5b21b6;
                }
                """
            )
        ))
    
    def _show_upgrade_dialog(self):
        """Show upgrade instructions - user needs a new license file"""
        if not self.license_client:
            return

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("License Upgrade")
        msg_box.setText(
            "To upgrade your license, please contact your administrator.\n\n"
            "They will provide you with a new license file (.lic).\n"
            "Click 'Import New License' to activate the new file."
        )
        msg_box.setStyleSheet("""
            QMessageBox { background-color: white; }
            QLabel { color: #1f2937; font-size: 13px; }
            QPushButton {
                background-color: #7c3aed; color: white; border: none;
                border-radius: 4px; padding: 8px 16px; font-size: 13px; min-width: 100px;
            }
            QPushButton:hover { background-color: #6d28d9; }
        """)

        import_btn = msg_box.addButton("Import New License", QMessageBox.AcceptRole)
        close_btn = msg_box.addButton("Close", QMessageBox.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == import_btn:
            self.license_client.deactivate()
            activation_dialog = ActivationDialog(self.license_client, self)
            activation_dialog.exec()
    
    
    def _show_license_info_dialog(self):
        """Show license information and management dialog"""
        if not self.license_client or not self.license_client.is_activated():
            return
        
        # Get license information
        license_info = self.license_client.get_license_info()
        trial_info = self.license_client.get_trial_info()

        license_id = license_info.get('license_id', license_info.get('license_key', 'N/A'))
        machine_id = license_info.get('machine_id', 'N/A')
        status = license_info.get('status', 'unknown')
        
        # Determine status display
        if trial_info and trial_info.get('is_trial'):
            days_remaining = trial_info.get('days_remaining', 0)
            expires_at_str = trial_info.get('expires_at_str', 'N/A')
            status_display = f"Trial ({days_remaining} days remaining)"
        elif status == 'active':
            # Check if it's purchased (not trial)
            if trial_info and not trial_info.get('is_trial'):
                status_display = "Active (Purchased)"
            else:
                status_display = "Active"
        elif status == 'expired':
            status_display = "Expired"
        else:
            status_display = status.title()
        
        # Create custom dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("License Management")
        dialog.setMinimumWidth(550)
        dialog.setMinimumHeight(500)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: white;
            }
            QLabel {
                color: #1f2937;
                font-size: 13px;
            }
            QLineEdit {
                padding: 10px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background-color: #f9fafb;
                color: #111827;
                font-size: 13px;
                font-family: 'Courier New', monospace;
            }
            QLineEdit:focus {
                border: 1px solid #7c3aed;
            }
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 500;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
            QPushButton:pressed {
                background-color: #5b21b6;
            }
            """
        )
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title_label = QLabel("License Management")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #111827; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # License ID section
        license_label = QLabel("License ID:")
        license_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #4b5563; margin-top: 10px;")
        layout.addWidget(license_label)

        license_key_layout = QHBoxLayout()
        license_key_input = QLineEdit(license_id)
        license_key_input.setReadOnly(True)
        license_key_layout.addWidget(license_key_input)

        copy_key_btn = QPushButton("Copy")
        copy_key_btn.setFixedWidth(100)
        copy_key_btn.clicked.connect(lambda: self._copy_to_clipboard(license_id, copy_key_btn))
        license_key_layout.addWidget(copy_key_btn)
        layout.addLayout(license_key_layout)
        
        # Machine ID section
        machine_label = QLabel("Machine ID:")
        machine_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #4b5563; margin-top: 10px;")
        layout.addWidget(machine_label)
        
        machine_id_layout = QHBoxLayout()
        machine_id_input = QLineEdit(machine_id)
        machine_id_input.setReadOnly(True)
        machine_id_layout.addWidget(machine_id_input)
        
        copy_machine_btn = QPushButton("📋 Copy")
        copy_machine_btn.setFixedWidth(100)
        copy_machine_btn.clicked.connect(lambda: self._copy_to_clipboard(machine_id, copy_machine_btn))
        machine_id_layout.addWidget(copy_machine_btn)
        layout.addLayout(machine_id_layout)
        
        # Status section
        status_label = QLabel("Status:")
        status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #4b5563; margin-top: 10px;")
        layout.addWidget(status_label)
        
        status_input = QLineEdit(status_display)
        status_input.setReadOnly(True)
        layout.addWidget(status_input)
        
        # Expiry date (if available)
        if trial_info:
            expires_at_str = trial_info.get('expires_at_str', 'N/A')
            expiry_label = QLabel("Expires:")
            expiry_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #4b5563; margin-top: 10px;")
            layout.addWidget(expiry_label)
            
            expiry_input = QLineEdit(expires_at_str)
            expiry_input.setReadOnly(True)
            layout.addWidget(expiry_input)
        
        layout.addStretch(1)
        
        # Upgrade License button (only show if it's a trial, not purchased)
        if trial_info and trial_info.get('is_trial'):
            upgrade_layout = QHBoxLayout()
            upgrade_layout.addStretch(1)
            upgrade_btn = QPushButton("Upgrade License")
            upgrade_btn.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 12px 25px;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 150px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
                QPushButton:pressed {
                    background-color: #1e7e34;
                }
            """)
            def on_upgrade_clicked():
                dialog.accept()
                self._show_upgrade_dialog()
            upgrade_btn.clicked.connect(on_upgrade_clicked)
            upgrade_layout.addWidget(upgrade_btn)
            upgrade_layout.addStretch(1)
            layout.addLayout(upgrade_layout)
        
        # Close button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)
        
        dialog.exec()
    
    def _show_tamper_popup(self):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Security Violation")
        msg_box.setText(
            "Security initialization failed.\n\n"
            "Encrypted configuration files are missing or corrupted.\n"
            "This installation may be tampered. Please contact your administrator."
        )
        msg_box.setStyleSheet(
            """
            QMessageBox {
                background-color: white;
            }
            QLabel {
                color: #1f2937;
                font-size: 13px;
            }
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            """
        )
        msg_box.exec()
    
    def _apply_responsive_layout(self):
        """Resize dialog based on available screen space"""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geometry = screen.availableGeometry()
        target_width = max(self.minimumWidth(), int(geometry.width() * 0.85))
        target_height = max(self.minimumHeight(), int(geometry.height() * 0.85))
        self.resize(target_width, target_height)
    
    
    def _on_login_clicked(self):
        """Handle login button click - check license first, then credentials"""
        import logging
        logger = logging.getLogger(__name__)

        # If licensing is enabled, validate license FIRST
        if self.licensing_enabled and self.license_client:
            logger.info("Login attempt started")

            # Check if activated
            if not self.license_client.is_activated():
                logger.warning("Login blocked: Not activated")
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.setWindowTitle("Activation Required")
                msg_box.setText("This application requires activation.\n\nPlease activate your license first.")
                msg_box.setStyleSheet("""
                    QMessageBox {
                        background-color: white;
                    }
                    QLabel {
                        color: #000000;
                        font-size: 13px;
                    }
                    QPushButton {
                        background-color: #7c3aed;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 8px 16px;
                        font-size: 13px;
                        min-width: 80px;
                    }
                    QPushButton:hover {
                        background-color: #6d28d9;
                    }
                """)
                msg_box.exec()

                # Show activation dialog
                activation_dialog = ActivationDialog(self.license_client, self)
                if activation_dialog.exec() != QDialog.Accepted:
                    return

            # Validate license offline (signature + machine + expiry)
            self._update_license_status("Validating...", "#3498db")
            valid, message = self.license_client.check_license()
            self.license_valid = valid

            if valid:
                self._update_license_status("License valid", "#28a745")
                logger.info("License validation passed")
                self._verify_credentials_and_login()
            else:
                self._update_license_status("License Invalid", "#dc3545")
                logger.warning(f"License validation failed: {message}")

                if "expired" in message.lower():
                    self._show_expired_dialog()
                else:
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Critical)
                    msg_box.setWindowTitle("License Validation Failed")
                    msg_box.setText(f"{message}\n\nPlease contact your administrator.")
                    msg_box.setStyleSheet("""
                        QMessageBox { background-color: white; }
                        QLabel { color: #1f2937; font-size: 13px; }
                        QPushButton {
                            background-color: #dc3545; color: white; border: none;
                            border-radius: 4px; padding: 8px 16px; font-size: 13px; min-width: 80px;
                        }
                        QPushButton:hover { background-color: #c82333; }
                    """)
                    msg_box.exec()
            return

        # If licensing disabled, proceed with credential check
        self._verify_credentials_and_login()
    
    def _verify_credentials_and_login(self):
        """Verify credentials after license is validated"""
        import logging
        logger = logging.getLogger(__name__)

        if self.licensing_enabled and self.license_client:
            if not self.license_valid:
                return

            entered_username = self.email_edit.text().strip()
            entered_password = self.password_edit.text()

            if not entered_username or not entered_password:
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.setWindowTitle("Missing Credentials")
                msg_box.setText("Please enter both username and password.")
                msg_box.setStyleSheet("""
                    QMessageBox { background-color: white; }
                    QLabel { color: #000000; font-size: 13px; }
                    QPushButton {
                        background-color: #7c3aed; color: white; border: none;
                        border-radius: 4px; padding: 8px 16px; font-size: 13px; min-width: 80px;
                    }
                    QPushButton:hover { background-color: #6d28d9; }
                """)
                msg_box.exec()
                return

            # Verify against stored credentials
            from pages.licensing.credentials import CredentialStorage
            cred_storage = CredentialStorage()

            is_valid = cred_storage.verify_credentials(entered_username, entered_password)

            if not is_valid:
                logger.warning("Login failed: Invalid credentials")
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Critical)
                msg_box.setWindowTitle("Login Failed")
                msg_box.setText("Invalid username or password.\n\n"
                               "Please contact your administrator if you've forgotten your credentials.")
                msg_box.setStyleSheet("""
                    QMessageBox { background-color: white; }
                    QLabel { color: #000000; font-size: 13px; }
                    QPushButton {
                        background-color: #dc3545; color: white; border: none;
                        border-radius: 4px; padding: 8px 16px; font-size: 13px; min-width: 80px;
                    }
                    QPushButton:hover { background-color: #c82333; }
                """)
                msg_box.exec()
                return

            logger.info("Login successful")

            # Show trial reminder if applicable
            trial_info = self.license_client.get_trial_info()
            if trial_info and trial_info.get('is_trial'):
                self._show_trial_reminder(trial_info)

            self.accept()
        else:
            # Licensing disabled, just accept
            self.accept()


class GradientWidget(QWidget):
    """Widget with decorative gradient background."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        gradient = QLinearGradient(0, 0, w, h)
        gradient.setColorAt(0.0, QColor("#f4d4ba"))
        gradient.setColorAt(0.3, QColor("#9b6fd8"))
        gradient.setColorAt(0.7, QColor("#7c3aed"))
        gradient.setColorAt(1.0, QColor("#6d28d9"))
        painter.fillRect(self.rect(), gradient)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(124, 58, 237, 180))
        painter.drawEllipse(int(-0.08 * w), int(0.18 * h), int(0.65 * w), int(0.7 * h))

        painter.setBrush(QColor(237, 187, 153, 120))
        painter.drawEllipse(int(0.42 * w), int(0.05 * h), int(0.35 * w), int(0.35 * h))

