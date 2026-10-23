"""
Admin Settings Dialog
Main admin panel for configuring operational settings
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QCheckBox, QRadioButton, QButtonGroup, QLineEdit, QGroupBox,
    QSpinBox, QFileDialog, QMessageBox, QScrollArea, QWidget
)
from .admin_config import AdminSettings, AdminConfigManager
from .admin_auth import AdminAuthManager


class AdminSettingsDialog(QDialog):
    """Main admin settings panel"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_manager = AdminConfigManager()
        self.settings = self.config_manager.load_settings()
        self._init_ui()
        self._load_settings_to_ui()
    
    def _init_ui(self):
        """Initialize UI components"""
        self.setWindowTitle("Admin Panel - Print Engine Settings")
        self.setModal(True)
        self.setMinimumSize(650, 750)
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header = QLabel("🔧 Admin Panel - Print Engine Settings")
        header.setStyleSheet("font-size: 16pt; font-weight: bold; color: #212529;")
        main_layout.addWidget(header)
        
        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(15)
        
        # 1. File Management Group
        content_layout.addWidget(self._create_file_management_group())
        
        # 2. Operator Controls Group
        content_layout.addWidget(self._create_operator_controls_group())
        
        # 3. Post-Print Actions Group
        content_layout.addWidget(self._create_post_print_group())
        
        # 4. Logging Group
        content_layout.addWidget(self._create_logging_group())
        
        # 5. Reprint Detection Group
        content_layout.addWidget(self._create_reprint_group())
        
        # 6. File Grouping Group
        content_layout.addWidget(self._create_file_grouping_group())
        
        # 7. Print Queue Performance Group
        content_layout.addWidget(self._create_performance_group())
        
        content_layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        
        # Change Password button (left)
        change_pwd_btn = QPushButton("Change Password")
        change_pwd_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: #212529;
                font-weight: bold;
                padding: 8px 15px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
        """)
        change_pwd_btn.clicked.connect(self._change_password)
        button_layout.addWidget(change_pwd_btn)
        
        button_layout.addStretch()
        
        # Save button
        save_btn = QPushButton("Save Settings")
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(save_btn)
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(button_layout)
    
    def _create_file_management_group(self) -> QGroupBox:
        """Create file management controls group"""
        group = QGroupBox("📁 File Management")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout()
        
        # Fix Browse Folder checkbox
        self.fix_folder_check = QCheckBox("Fix Browse File Folder (Lock folder selection)")
        self.fix_folder_check.toggled.connect(self._on_fix_folder_toggled)
        layout.addWidget(self.fix_folder_check)
        
        # Fixed folder path 1
        folder_row = QHBoxLayout()
        folder_row.addSpacing(30)
        self.fixed_folder_label = QLabel("Fixed Folder Path 1:")
        folder_row.addWidget(self.fixed_folder_label)
        
        self.fixed_folder_input = QLineEdit()
        self.fixed_folder_input.setPlaceholderText("Select folder...")
        self.fixed_folder_input.setReadOnly(True)
        folder_row.addWidget(self.fixed_folder_input)
        
        self.browse_folder_btn = QPushButton("Browse...")
        self.browse_folder_btn.clicked.connect(self._browse_fixed_folder)
        folder_row.addWidget(self.browse_folder_btn)
        
        layout.addLayout(folder_row)
        
        # Info label for folder 1
        info1_row = QHBoxLayout()
        info1_row.addSpacing(30)
        info1 = QLabel("ℹ️ Used by: Single Server, Dual Server Folder 1")
        info1.setStyleSheet("color: #6c757d; font-size: 9pt; font-style: italic;")
        info1_row.addWidget(info1)
        info1_row.addStretch()
        layout.addLayout(info1_row)
        
        # Fixed folder path 2
        folder2_row = QHBoxLayout()
        folder2_row.addSpacing(30)
        self.fixed_folder2_label = QLabel("Fixed Folder Path 2:")
        folder2_row.addWidget(self.fixed_folder2_label)
        
        self.fixed_folder2_input = QLineEdit()
        self.fixed_folder2_input.setPlaceholderText("Optional - for Dual Server separate mode...")
        self.fixed_folder2_input.setReadOnly(True)
        folder2_row.addWidget(self.fixed_folder2_input)
        
        self.browse_folder2_btn = QPushButton("Browse...")
        self.browse_folder2_btn.clicked.connect(self._browse_fixed_folder2)
        folder2_row.addWidget(self.browse_folder2_btn)
        
        layout.addLayout(folder2_row)
        
        # Info label for folder 2
        info2_row = QHBoxLayout()
        info2_row.addSpacing(30)
        info2 = QLabel("ℹ️ Used by: Dual Server Folder 2 (separate folders mode only)")
        info2.setStyleSheet("color: #6c757d; font-size: 9pt; font-style: italic;")
        info2_row.addWidget(info2)
        info2_row.addStretch()
        layout.addLayout(info2_row)
        
        # Auto-refresh checkbox
        refresh_row = QHBoxLayout()
        refresh_row.addSpacing(30)
        self.auto_refresh_check = QCheckBox("Auto-refresh file list every")
        refresh_row.addWidget(self.auto_refresh_check)
        
        self.refresh_interval_spin = QSpinBox()
        self.refresh_interval_spin.setRange(1, 60)
        self.refresh_interval_spin.setValue(5)
        self.refresh_interval_spin.setSuffix(" sec")
        refresh_row.addWidget(self.refresh_interval_spin)
        
        refresh_row.addStretch()
        layout.addLayout(refresh_row)
        
        group.setLayout(layout)
        return group
    
    def _create_operator_controls_group(self) -> QGroupBox:
        """Create operator controls group"""
        group = QGroupBox("🎛️ Operator Controls")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout()
        
        info = QLabel("Enable/disable operator access to these controls:")
        info.setStyleSheet("color: #6c757d; font-size: 9pt; font-weight: normal;")
        layout.addWidget(info)
        
        self.enable_copies_check = QCheckBox("Enable Copies / Collate controls")
        layout.addWidget(self.enable_copies_check)
        
        self.enable_range_check = QCheckBox("Enable Specify Range option")
        layout.addWidget(self.enable_range_check)
        
        self.enable_reverse_check = QCheckBox("Enable Reverse Order option")
        layout.addWidget(self.enable_reverse_check)
        
        self.enable_continuous_check = QCheckBox("Enable Continuous Mode option")
        layout.addWidget(self.enable_continuous_check)
        
        group.setLayout(layout)
        return group
    
    def _create_post_print_group(self) -> QGroupBox:
        """Create post-print actions group"""
        group = QGroupBox("📄 Post-Print File Actions")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout()
        
        info = QLabel("Action to perform after successful print job completion:")
        info.setStyleSheet("color: #6c757d; font-size: 9pt; font-weight: normal;")
        layout.addWidget(info)
        
        # Radio button group
        self.post_print_group = QButtonGroup(self)
        
        self.no_action_radio = QRadioButton("No Action (keep files in folder)")
        self.post_print_group.addButton(self.no_action_radio, 0)
        layout.addWidget(self.no_action_radio)
        
        self.delete_radio = QRadioButton("Delete Files (permanent deletion, not to recycle bin)")
        self.delete_radio.setStyleSheet("QRadioButton { color: #dc3545; }")
        self.post_print_group.addButton(self.delete_radio, 1)
        layout.addWidget(self.delete_radio)
        
        self.move_radio = QRadioButton("Move Files to destination folder:")
        self.post_print_group.addButton(self.move_radio, 2)
        self.move_radio.toggled.connect(self._on_move_toggled)
        layout.addWidget(self.move_radio)
        
        # Move destination
        move_row = QHBoxLayout()
        move_row.addSpacing(30)
        self.move_dest_input = QLineEdit()
        self.move_dest_input.setPlaceholderText("Select destination folder...")
        self.move_dest_input.setReadOnly(True)
        move_row.addWidget(self.move_dest_input)
        
        self.browse_dest_btn = QPushButton("Browse...")
        self.browse_dest_btn.clicked.connect(self._browse_move_destination)
        move_row.addWidget(self.browse_dest_btn)
        
        layout.addLayout(move_row)
        
        # Move destination 2 (Dual Server)
        self.move_dest_2_label = QLabel("Destination 2 (Dual Server - Folder 2):")
        self.move_dest_2_label.setStyleSheet("color: #6c757d; margin-left: 30px;")
        layout.addWidget(self.move_dest_2_label)
        
        move_row_2 = QHBoxLayout()
        move_row_2.addSpacing(30)
        self.move_dest_2_input = QLineEdit()
        self.move_dest_2_input.setPlaceholderText("Select destination for Folder 2 (optional)...")
        self.move_dest_2_input.setReadOnly(True)
        move_row_2.addWidget(self.move_dest_2_input)
        
        self.browse_dest_2_btn = QPushButton("Browse...")
        self.browse_dest_2_btn.clicked.connect(self._browse_move_destination_2)
        move_row_2.addWidget(self.browse_dest_2_btn)
        
        layout.addLayout(move_row_2)
        
        group.setLayout(layout)
        return group
    
    def _create_logging_group(self) -> QGroupBox:
        """Create logging controls group"""
        group = QGroupBox("📊 Production Logging")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout()
        
        self.logging_enabled_check = QCheckBox("Enable Production Logging")
        self.logging_enabled_check.toggled.connect(self._on_logging_toggled)
        layout.addWidget(self.logging_enabled_check)
        
        info = QLabel("Log includes: file names, page numbers, copies, timestamps")
        info.setStyleSheet("color: #6c757d; font-size: 9pt; font-weight: normal;")
        layout.addWidget(info)
        
        # Logging mode
        mode_row = QHBoxLayout()
        mode_row.addSpacing(30)
        mode_row.addWidget(QLabel("Log aggregation:"))
        
        self.log_mode_group = QButtonGroup(self)
        
        self.log_daily_radio = QRadioButton("Daily")
        self.log_mode_group.addButton(self.log_daily_radio, 0)
        mode_row.addWidget(self.log_daily_radio)
        
        self.log_monthly_radio = QRadioButton("Monthly")
        self.log_mode_group.addButton(self.log_monthly_radio, 1)
        mode_row.addWidget(self.log_monthly_radio)
        
        self.log_yearly_radio = QRadioButton("Yearly")
        self.log_mode_group.addButton(self.log_yearly_radio, 2)
        mode_row.addWidget(self.log_yearly_radio)
        
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Add "View Logs" button row
        view_logs_row = QHBoxLayout()
        view_logs_row.addSpacing(30)

        self.view_logs_btn = QPushButton("📊 View Production Logs")
        self.view_logs_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 15px;
                border-radius: 4px;
                min-width: 180px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                color: #adb5bd;
            }
        """)
        self.view_logs_btn.setToolTip("Open log viewer to view and export production logs")
        self.view_logs_btn.clicked.connect(self._on_view_logs)
        self.view_logs_btn.setEnabled(False)  # Disabled by default
        view_logs_row.addWidget(self.view_logs_btn)

        view_logs_row.addStretch()
        layout.addLayout(view_logs_row)

        group.setLayout(layout)
        return group
    
    def _create_reprint_group(self) -> QGroupBox:
        """Create reprint detection group"""
        group = QGroupBox("🔄 Reprint Detection")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout()
        
        # Enable checkbox
        self.reprint_enabled_check = QCheckBox("Enable Reprint Detection")
        self.reprint_enabled_check.toggled.connect(self._on_reprint_toggled)
        layout.addWidget(self.reprint_enabled_check)
        
        info = QLabel("Check for duplicate files before printing (uses filename + size + modification time)")
        info.setStyleSheet("color: #6c757d; font-size: 9pt; font-weight: normal;")
        layout.addWidget(info)
        
        # Detection mode (indented under enable checkbox)
        mode_layout = QVBoxLayout()
        mode_layout.setContentsMargins(30, 5, 0, 5)
        
        self.reprint_mode_group = QButtonGroup(self)
        
        self.reprint_allowed_radio = QRadioButton("Allowed (no blocking, history tracked)")
        self.reprint_mode_group.addButton(self.reprint_allowed_radio, 0)
        mode_layout.addWidget(self.reprint_allowed_radio)
        
        self.reprint_warning_radio = QRadioButton("Warning (show warning, allow to continue)")
        self.reprint_warning_radio.setStyleSheet("QRadioButton { color: #ffc107; }")
        self.reprint_mode_group.addButton(self.reprint_warning_radio, 1)
        mode_layout.addWidget(self.reprint_warning_radio)
        
        self.reprint_blocked_radio = QRadioButton("Not Allowed (block reprint with error)")
        self.reprint_blocked_radio.setStyleSheet("QRadioButton { color: #dc3545; }")
        self.reprint_mode_group.addButton(self.reprint_blocked_radio, 2)
        mode_layout.addWidget(self.reprint_blocked_radio)
        
        layout.addLayout(mode_layout)
        
        # History retention
        retention_row = QHBoxLayout()
        retention_row.addSpacing(30)
        retention_row.addWidget(QLabel("History Retention:"))
        
        self.retention_days_spin = QSpinBox()
        self.retention_days_spin.setRange(1, 365)
        self.retention_days_spin.setValue(90)
        self.retention_days_spin.setSuffix(" days")
        self.retention_days_spin.setToolTip("Auto-delete records older than this")
        retention_row.addWidget(self.retention_days_spin)
        
        retention_row.addStretch()
        layout.addLayout(retention_row)
        
        # History management buttons
        button_row = QHBoxLayout()
        button_row.addSpacing(30)
        
        view_history_btn = QPushButton("View History")
        view_history_btn.clicked.connect(self._on_view_history)
        button_row.addWidget(view_history_btn)
        
        clear_history_btn = QPushButton("Clear History")
        clear_history_btn.setStyleSheet("background-color: #dc3545; color: white;")
        clear_history_btn.clicked.connect(self._on_clear_history)
        button_row.addWidget(clear_history_btn)
        
        button_row.addStretch()
        layout.addLayout(button_row)
        
        group.setLayout(layout)
        return group
    
    def _on_fix_folder_toggled(self, checked):
        """Handle fix folder checkbox toggle"""
        self.fixed_folder_label.setEnabled(checked)
        self.fixed_folder_input.setEnabled(checked)
        self.browse_folder_btn.setEnabled(checked)
        self.fixed_folder2_label.setEnabled(checked)
        self.fixed_folder2_input.setEnabled(checked)
        self.browse_folder2_btn.setEnabled(checked)
        self.auto_refresh_check.setEnabled(checked)
        self.refresh_interval_spin.setEnabled(checked and self.auto_refresh_check.isChecked())
    
    def _on_move_toggled(self, checked):
        """Handle move radio toggle"""
        self.move_dest_input.setEnabled(checked)
        self.browse_dest_btn.setEnabled(checked)
        self.move_dest_2_label.setEnabled(checked)
        self.move_dest_2_input.setEnabled(checked)
        self.browse_dest_2_btn.setEnabled(checked)
    
    def _on_logging_toggled(self, checked):
        """Handle logging checkbox toggle"""
        self.log_daily_radio.setEnabled(checked)
        self.log_monthly_radio.setEnabled(checked)
        self.log_yearly_radio.setEnabled(checked)
        self.view_logs_btn.setEnabled(checked)

    def _on_reprint_toggled(self, checked):
        """Handle reprint detection checkbox toggle"""
        self.reprint_allowed_radio.setEnabled(checked)
        self.reprint_warning_radio.setEnabled(checked)
        self.reprint_blocked_radio.setEnabled(checked)
        self.retention_days_spin.setEnabled(checked)

    def _on_view_logs(self):
        """Open production log viewer dialog"""
        try:
            from .production_log_viewer_dialog import ProductionLogViewerDialog

            dialog = ProductionLogViewerDialog(self)
            dialog.exec()

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open production log viewer:\n{str(e)}"
            )

    def _create_file_grouping_group(self) -> QGroupBox:
        """Create file grouping controls group"""
        group = QGroupBox("📑 Multi-PDF File Grouping")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout()
        
        # Enable checkbox
        self.file_grouping_check = QCheckBox("Enable Multi-PDF File Grouping")
        self.file_grouping_check.setToolTip(
            "When enabled, shows file groups when multiple PDFs are detected in same folder.\n"
            "Allows selection and reordering of PDF groups before printing."
        )
        layout.addWidget(self.file_grouping_check)
        
        # Info label
        info = QLabel(
            "When multiple PDFs are ripped to the same folder, this feature groups files by PDF name\n"
            "and allows you to select which groups to print and in what order."
        )
        info.setStyleSheet("color: #6c757d; font-size: 9pt; margin-left: 25px;")
        layout.addWidget(info)
        
        group.setLayout(layout)
        return group
    
    def _create_performance_group(self) -> QGroupBox:
        """Create print queue performance controls group"""
        group = QGroupBox("⚡ Print Queue Performance")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 11pt;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout()
        
        # Info label
        info = QLabel(
            "Configure how many files are sent to the printer queue at once.\n"
            "Higher values = faster queuing, Lower values = more stable for slower networks."
        )
        info.setStyleSheet("color: #6c757d; font-size: 9pt; font-weight: normal;")
        layout.addWidget(info)
        
        # Batch size control
        batch_row = QHBoxLayout()
        batch_row.addWidget(QLabel("Batch Size:"))
        
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 9999)  # No upper limit (up to 9999)
        self.batch_size_spin.setValue(10)
        self.batch_size_spin.setToolTip(
            "Number of files to send to printer queue before checking responses.\n"
            "Default: 10 files\n"
            "Range: 1-9999 files (unlimited)\n"
            "Recommended: 10-50 for most networks\n"
            "⚠️ Very high values require fast networks and sufficient server memory"
        )
        self.batch_size_spin.valueChanged.connect(self._on_batch_size_changed)
        batch_row.addWidget(self.batch_size_spin)

        batch_row.addWidget(QLabel("files"))
        batch_row.addStretch()
        layout.addLayout(batch_row)

        # Warning label for high batch sizes
        self.batch_warning_label = QLabel("")
        self.batch_warning_label.setStyleSheet("color: #ff6b6b; font-size: 9pt; font-style: italic;")
        self.batch_warning_label.setWordWrap(True)
        layout.addWidget(self.batch_warning_label)
        
        # Resume behavior control
        resume_row = QHBoxLayout()
        resume_row.addWidget(QLabel("Pages to re-print on resume:"))
        
        self.resume_repeat_spin = QSpinBox()
        self.resume_repeat_spin.setRange(0, 50)
        self.resume_repeat_spin.setValue(1)
        self.resume_repeat_spin.setToolTip(
            "How many previously printed pages should be re-sent when resuming a stopped job.\n"
            "0 = resume from next page without re-printing, 1 = last page only (default),\n"
            "2 or more = go back that many pages and re-print them for safety."
        )
        resume_row.addWidget(self.resume_repeat_spin)
        resume_row.addWidget(QLabel("page(s)"))
        resume_row.addStretch()
        layout.addLayout(resume_row)
        
        group.setLayout(layout)
        return group
    
    def _browse_fixed_folder(self):
        """Browse for fixed folder path 1"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Fixed RIP Folder Path 1",
            self.fixed_folder_input.text() or ""
        )
        if folder:
            self.fixed_folder_input.setText(folder)
    
    def _browse_fixed_folder2(self):
        """Browse for fixed folder path 2"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Fixed RIP Folder Path 2 (Dual Server)",
            self.fixed_folder2_input.text() or ""
        )
        if folder:
            self.fixed_folder2_input.setText(folder)
    
    def _browse_move_destination(self):
        """Browse for move destination folder"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Move Destination Folder",
            self.move_dest_input.text() or ""
        )
        if folder:
            self.move_dest_input.setText(folder)
            
    def _browse_move_destination_2(self):
        """Browse for move destination folder 2"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Move Destination Folder 2 (Dual Server)",
            self.move_dest_2_input.text() or ""
        )
        if folder:
            self.move_dest_2_input.setText(folder)
    
    def _load_settings_to_ui(self):
        """Load settings from model to UI controls"""
        # File Management
        self.fix_folder_check.setChecked(self.settings.fix_browse_folder)
        self.fixed_folder_input.setText(self.settings.fixed_folder_path)
        self.fixed_folder2_input.setText(self.settings.fixed_folder_path_2)
        self.auto_refresh_check.setChecked(self.settings.auto_refresh_enabled)
        self.refresh_interval_spin.setValue(self.settings.auto_refresh_interval)
        
        # Operator Controls
        self.enable_copies_check.setChecked(self.settings.enable_copies_collate)
        self.enable_range_check.setChecked(self.settings.enable_specify_range)
        self.enable_reverse_check.setChecked(self.settings.enable_reverse_order)
        self.enable_continuous_check.setChecked(self.settings.enable_continuous_mode)
        
        # Post-Print Actions
        if self.settings.post_print_action == "no_action":
            self.no_action_radio.setChecked(True)
        elif self.settings.post_print_action == "delete":
            self.delete_radio.setChecked(True)
        elif self.settings.post_print_action == "move":
            self.move_radio.setChecked(True)
        self.move_dest_input.setText(self.settings.move_destination)
        self.move_dest_2_input.setText(self.settings.move_destination_2)
        
        # Logging
        self.logging_enabled_check.setChecked(self.settings.logging_enabled)
        if self.settings.logging_mode == "daily":
            self.log_daily_radio.setChecked(True)
        elif self.settings.logging_mode == "monthly":
            self.log_monthly_radio.setChecked(True)
        elif self.settings.logging_mode == "yearly":
            self.log_yearly_radio.setChecked(True)

        # Update View Logs button state
        self.view_logs_btn.setEnabled(self.settings.logging_enabled)

        # Reprint Detection
        self.reprint_enabled_check.setChecked(self.settings.enable_reprint_detection)
        if self.settings.reprint_mode == "allowed":
            self.reprint_allowed_radio.setChecked(True)
        elif self.settings.reprint_mode == "warning":
            self.reprint_warning_radio.setChecked(True)
        elif self.settings.reprint_mode == "not_allowed":
            self.reprint_blocked_radio.setChecked(True)
        self.retention_days_spin.setValue(self.settings.history_retention_days)
        
        # File Grouping
        self.file_grouping_check.setChecked(self.settings.enable_file_grouping)
        
        # Print Queue Performance
        self.batch_size_spin.setValue(self.settings.batch_size)
        
        # Resume behavior
        if hasattr(self.settings, "resume_repeat_pages"):
            try:
                self.resume_repeat_spin.setValue(int(self.settings.resume_repeat_pages))
            except Exception:
                self.resume_repeat_spin.setValue(1)
        
        # Trigger initial state updates
        self._on_fix_folder_toggled(self.fix_folder_check.isChecked())
        self._on_move_toggled(self.move_radio.isChecked())
        self._on_logging_toggled(self.logging_enabled_check.isChecked())
        self._on_reprint_toggled(self.reprint_enabled_check.isChecked())
    
    def _save_settings_to_model(self):
        """Save UI controls to settings model"""
        # File Management
        self.settings.fix_browse_folder = self.fix_folder_check.isChecked()
        self.settings.fixed_folder_path = self.fixed_folder_input.text()
        self.settings.fixed_folder_path_2 = self.fixed_folder2_input.text()
        self.settings.auto_refresh_enabled = self.auto_refresh_check.isChecked()
        self.settings.auto_refresh_interval = self.refresh_interval_spin.value()
        
        # Operator Controls
        self.settings.enable_copies_collate = self.enable_copies_check.isChecked()
        self.settings.enable_specify_range = self.enable_range_check.isChecked()
        self.settings.enable_reverse_order = self.enable_reverse_check.isChecked()
        self.settings.enable_continuous_mode = self.enable_continuous_check.isChecked()
        
        # Post-Print Actions
        if self.no_action_radio.isChecked():
            self.settings.post_print_action = "no_action"
        elif self.delete_radio.isChecked():
            self.settings.post_print_action = "delete"
        elif self.move_radio.isChecked():
            self.settings.post_print_action = "move"
        self.settings.move_destination = self.move_dest_input.text()
        self.settings.move_destination_2 = self.move_dest_2_input.text()
        
        # Logging
        self.settings.logging_enabled = self.logging_enabled_check.isChecked()
        if self.log_daily_radio.isChecked():
            self.settings.logging_mode = "daily"
        elif self.log_monthly_radio.isChecked():
            self.settings.logging_mode = "monthly"
        elif self.log_yearly_radio.isChecked():
            self.settings.logging_mode = "yearly"
        
        # Reprint Detection
        self.settings.enable_reprint_detection = self.reprint_enabled_check.isChecked()
        if self.reprint_allowed_radio.isChecked():
            self.settings.reprint_mode = "allowed"
        elif self.reprint_warning_radio.isChecked():
            self.settings.reprint_mode = "warning"
        elif self.reprint_blocked_radio.isChecked():
            self.settings.reprint_mode = "not_allowed"
        self.settings.history_retention_days = self.retention_days_spin.value()
        
        # File Grouping
        self.settings.enable_file_grouping = self.file_grouping_check.isChecked()
        
        # Print Queue Performance
        self.settings.batch_size = self.batch_size_spin.value()
        
        # Resume behavior
        try:
            self.settings.resume_repeat_pages = max(0, int(self.resume_repeat_spin.value()))
        except Exception:
            self.settings.resume_repeat_pages = 1

    def _on_batch_size_changed(self, value):
        """Show warning when batch size is set high"""
        if value > 500:
            self.batch_warning_label.setText(
                "🔴 EXTREME: This may cause serious issues! "
                "Only use if you have verified server capacity and network stability. "
                "Pipeline will be capped at safe limits automatically."
            )
            self.batch_warning_label.setStyleSheet("color: #dc3545; font-size: 10pt; font-weight: bold;")
        elif value > 200:
            self.batch_warning_label.setText(
                "⚠️ Very High: Requires very fast network and large server memory. "
                "Test thoroughly in non-production environment first. "
                "Automatic safety limits will apply."
            )
            self.batch_warning_label.setStyleSheet("color: #ff6b6b; font-size: 9pt; font-style: italic;")
        elif value > 100:
            self.batch_warning_label.setText(
                "⚠️ High: May cause issues on slower networks or limited memory. "
                "Ensure server has sufficient queue capacity."
            )
            self.batch_warning_label.setStyleSheet("color: #ff9f43; font-size: 9pt; font-style: italic;")
        elif value > 50:
            self.batch_warning_label.setText(
                "ℹ️ Above recommended: Test before production use."
            )
            self.batch_warning_label.setStyleSheet("color: #ffa502; font-size: 9pt; font-style: italic;")
        else:
            self.batch_warning_label.setText("")
            self.batch_warning_label.setStyleSheet("color: #6c757d; font-size: 9pt;")

    def _save_settings(self):
        """Save settings and close dialog"""
        # Validate settings
        if self.fix_folder_check.isChecked() and not self.fixed_folder_input.text():
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please select a fixed folder path."
            )
            return
        
        # Validate fixed folder 2 if provided
        if self.fix_folder_check.isChecked() and self.fixed_folder2_input.text():
            folder2_path = Path(self.fixed_folder2_input.text())
            if not folder2_path.exists() or not folder2_path.is_dir():
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Fixed folder path 2 does not exist or is not a directory:\n{self.fixed_folder2_input.text()}"
                )
                return
        
        if self.move_radio.isChecked() and not self.move_dest_input.text():
            QMessageBox.warning(
                self,
                "Validation Error",
                "Please select a move destination folder."
            )
            return
        
        # Save to model
        self._save_settings_to_model()
        
        # Persist to file
        if self.config_manager.save_settings(self.settings):
            QMessageBox.information(
                self,
                "Settings Saved",
                "Admin settings have been saved successfully."
            )
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "Save Error",
                "Failed to save admin settings. Please try again."
            )
    
    def _change_password(self):
        """Change admin password"""
        from .admin_password_entry_dialog import AdminPasswordEntryDialog
        from .admin_password_setup_dialog import AdminPasswordSetupDialog
        
        auth_manager = AdminAuthManager()
        
        # Verify current password
        verify_dialog = AdminPasswordEntryDialog(self)
        verify_dialog.setWindowTitle("Verify Current Password")
        
        if verify_dialog.exec() != QDialog.Accepted:
            return
        
        old_password = verify_dialog.get_password()
        if not auth_manager.verify_password(old_password):
            QMessageBox.critical(
                self,
                "Authentication Failed",
                "Current password is incorrect."
            )
            return
        
        # Get new password
        setup_dialog = AdminPasswordSetupDialog(self)
        setup_dialog.setWindowTitle("Set New Password")
        
        if setup_dialog.exec() == QDialog.Accepted:
            new_password = setup_dialog.get_password()
            if auth_manager.change_password(old_password, new_password):
                QMessageBox.information(
                    self,
                    "Password Changed",
                    "Admin password has been changed successfully."
                )
            else:
                QMessageBox.critical(
                    self,
                    "Change Failed",
                    "Failed to change password. Please try again."
                )
    
    def _on_view_history(self):
        """Open print history viewer dialog"""
        try:
            from .print_history_dialog import PrintHistoryDialog
            
            dialog = PrintHistoryDialog(self)
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open print history:\n{str(e)}"
            )
    
    def _on_clear_history(self):
        """Clear all print history with confirmation"""
        reply = QMessageBox.question(
            self,
            "Clear Print History",
            "Are you sure you want to clear all print history?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                from .print_history_db import PrintHistoryDB
                
                db = PrintHistoryDB()
                success = db.clear_history()
                
                if success:
                    QMessageBox.information(
                        self,
                        "Success",
                        "Print history cleared successfully."
                    )
                else:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "Failed to clear print history."
                    )
                    
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to clear print history:\n{str(e)}"
                )
