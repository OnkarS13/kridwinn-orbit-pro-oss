from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QLabel
from .single_server.single_server_widget import SingleServerWidget
from .dual_server.dual_server_widget import DualServerWidget


class RIP2PrintSection(QWidget):
    """
    RIP2PRINT mode container with a centered two-button menu (Single/Dual).
    Clicking a button opens the respective UI with a back button to return.
    """

    def __init__(self, server_manager=None, parent=None):
        super().__init__(parent)
        self.server_manager = server_manager
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Build content pages
        self.stack = QStackedWidget()

        # 1) MENU page (two large centered buttons)
        self.menu_page = QWidget()
        menu_v = QVBoxLayout(self.menu_page)
        menu_v.setContentsMargins(0, 0, 0, 0)
        
        # Header with Admin Panel button
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        
        admin_btn = QPushButton("⚙️ Admin Panel")
        admin_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 11pt;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        admin_btn.setToolTip("Access admin settings (password required)")
        admin_btn.clicked.connect(self._open_admin_panel)
        header_layout.addWidget(admin_btn)
        
        menu_v.addLayout(header_layout)
        menu_v.addStretch(2)
        
        row = QHBoxLayout()
        row.addStretch()

        single_btn = QPushButton("Single Server")
        single_btn.setMinimumSize(200, 80)
        single_btn.setStyleSheet(
            """
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #0056b3; }
            """
        )
        single_btn.clicked.connect(lambda: self._show_job("single"))
        row.addWidget(single_btn)
        row.addSpacing(40)

        dual_btn = QPushButton("Dual Server")
        dual_btn.setMinimumSize(200, 80)
        dual_btn.setStyleSheet(
            """
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #28a745; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #218838; }
            """
        )
        dual_btn.clicked.connect(lambda: self._show_job("dual"))
        row.addWidget(dual_btn)
        row.addStretch()
        menu_v.addLayout(row)
        menu_v.addStretch(3)

        # 2) SINGLE job page (back + existing widget)
        self.single = SingleServerWidget(server_manager)
        self.single_page = QWidget()
        s_v = QVBoxLayout(self.single_page)
        s_back = QPushButton("← Back to RIP2PRINT")
        s_back.setMaximumWidth(220)
        s_back.setStyleSheet(
            """
            QPushButton { background-color: #6c757d; color: white; font-weight: 600; padding: 8px 14px; border: none; border-radius: 6px; }
            QPushButton:hover { background-color: #5a6268; }
            """
        )
        s_back.clicked.connect(self._show_menu)
        header_s = QHBoxLayout()
        header_s.addWidget(s_back)
        header_s.addStretch()
        title_single = QLabel("Single Server")
        title_single.setStyleSheet("font-size: 16pt; font-weight: bold; color: #212529;")
        header_s.addWidget(title_single)
        s_v.addLayout(header_s)
        s_v.addWidget(self.single)

        # 3) DUAL job page (back + existing widget)
        self.dual = DualServerWidget(server_manager)
        self.dual_page = QWidget()
        d_v = QVBoxLayout(self.dual_page)
        d_back = QPushButton("← Back to RIP2PRINT")
        d_back.setMaximumWidth(220)
        d_back.setStyleSheet(
            """
            QPushButton { background-color: #6c757d; color: white; font-weight: 600; padding: 8px 14px; border: none; border-radius: 6px; }
            QPushButton:hover { background-color: #5a6268; }
            """
        )
        d_back.clicked.connect(self._show_menu)
        header_d = QHBoxLayout()
        header_d.addWidget(d_back)
        header_d.addStretch()
        title_dual = QLabel("Dual Server")
        title_dual.setStyleSheet("font-size: 16pt; font-weight: bold; color: #212529;")
        header_d.addWidget(title_dual)
        d_v.addLayout(header_d)
        d_v.addWidget(self.dual)

        # Add pages to stack
        self.stack.addWidget(self.menu_page)
        self.stack.addWidget(self.single_page)
        self.stack.addWidget(self.dual_page)

        root.addWidget(self.stack)
        self._show_menu()

    def _show_menu(self):
        self.stack.setCurrentWidget(self.menu_page)

    def _show_job(self, which: str):
        if which == "single":
            # Ensure dropdowns reflect current server list
            try:
                self.single._populate_servers()
            except Exception:
                pass
            self.stack.setCurrentWidget(self.single_page)
        else:
            try:
                self.dual._populate_servers()
            except Exception:
                pass
            self.stack.setCurrentWidget(self.dual_page)

    def set_server_manager(self, manager):
        """Update server manager reference and repopulate dropdowns."""
        self.server_manager = manager
        try:
            self.single.server_manager = manager
            self.single._populate_servers()
        except Exception:
            pass
        try:
            self.dual.server_manager = manager
            self.dual._populate_servers()
        except Exception:
            pass
    
    def _open_admin_panel(self):
        """Open admin panel with password authentication"""
        from ..shared.admin_auth import AdminAuthManager
        from ..shared.admin_password_setup_dialog import AdminPasswordSetupDialog
        from ..shared.admin_password_entry_dialog import AdminPasswordEntryDialog
        from ..shared.admin_settings_dialog import AdminSettingsDialog
        from PySide6.QtWidgets import QDialog, QMessageBox
        
        auth_manager = AdminAuthManager()
        
        # Check if password is set
        if not auth_manager.is_password_set():
            # First-time setup
            setup_dialog = AdminPasswordSetupDialog(self)
            if setup_dialog.exec() == QDialog.Accepted:
                password = setup_dialog.get_password()
                if auth_manager.set_password(password):
                    QMessageBox.information(
                        self,
                        "Password Set",
                        "Admin password has been set successfully.\\n\\nYou can now access the admin panel."
                    )
                    # Open admin settings
                    self._show_admin_settings()
                else:
                    QMessageBox.critical(
                        self,
                        "Setup Failed",
                        "Failed to set admin password. Please try again."
                    )
        else:
            # Authenticate
            entry_dialog = AdminPasswordEntryDialog(self)
            if entry_dialog.exec() == QDialog.Accepted:
                password = entry_dialog.get_password()
                if auth_manager.verify_password(password):
                    # Open admin settings
                    self._show_admin_settings()
                else:
                    QMessageBox.critical(
                        self,
                        "Authentication Failed",
                        "Invalid password. Access denied."
                    )
                    entry_dialog.show_error("Invalid password")
    
    def _show_admin_settings(self):
        """Show admin settings dialog"""
        from ..shared.admin_settings_dialog import AdminSettingsDialog
        from PySide6.QtWidgets import QDialog
        
        settings_dialog = AdminSettingsDialog(self)
        if settings_dialog.exec() == QDialog.Accepted:
            # Reload and apply settings in both widgets
            try:
                self.single._load_and_apply_admin_settings()
            except Exception as e:
                print(f"Error reloading settings in Single Server: {e}")
            
            try:
                self.dual._load_and_apply_admin_settings()
            except Exception as e:
                print(f"Error reloading settings in Dual Server: {e}")


