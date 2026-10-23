"""
Server Control Widget - Individual printer server control panel
"""
import os
import time
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QSpinBox, QComboBox, QCheckBox, QRadioButton, QButtonGroup,
    QProgressBar, QTextEdit, QFileDialog, QScrollArea
)
from .shared.server_config import PrinterServerConfig


class ServerControlWidget(QWidget):
    """Control panel for a single printer server"""
    
    # Signals
    start_printing_requested = Signal(str)  # server_id
    stop_printing_requested = Signal(str)   # server_id
    
    def __init__(self, server_id: str, server_config: PrinterServerConfig, parent=None):
        super().__init__(parent)
        self.server_id = server_id
        self.config = server_config
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left side: Controls (scrollable)
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(20)
        
        # === HEADER: Server Info ===
        header_group = self._create_header_section()
        controls_layout.addWidget(header_group)
        
        # === RIP Folder Selection ===
        folder_group = self._create_folder_section()
        controls_layout.addWidget(folder_group)
        
        # === Print Settings ===
        settings_group = self._create_settings_section()
        controls_layout.addWidget(settings_group)
        
        # === Page Selection ===
        page_group = self._create_page_selection_section()
        controls_layout.addWidget(page_group)
        
        # === Progress ===
        progress_group = self._create_progress_section()
        controls_layout.addWidget(progress_group)
        
        # === Action Buttons ===
        actions_group = self._create_actions_section()
        controls_layout.addWidget(actions_group)
        
        controls_layout.addStretch()
        
        # Make controls scrollable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(controls_widget)
        scroll.setMinimumWidth(380)
        scroll.setMaximumWidth(450)
        
        main_layout.addWidget(scroll)
        
        # Right side: Status and Logs
        status_widget = self._create_status_section()
        main_layout.addWidget(status_widget, 1)
        
        # Set proportions
        main_layout.setStretch(0, 0)  # Fixed width for controls
        main_layout.setStretch(1, 1)  # Flexible for status
    
    def _create_header_section(self):
        """Create header with server info and connection status"""
        group = QGroupBox()
        layout = QVBoxLayout()
        
        # Server name
        name_label = QLabel(f"<h3>{self.config.name}</h3>")
        layout.addWidget(name_label)
        
        # Connection status
        status_layout = QHBoxLayout()
        self.status_light = QLabel("●")
        self.status_light.setStyleSheet("color: #dc3545; font-size: 16pt;")
        self.status_text = QLabel("Not Connected")
        self.status_text.setStyleSheet("color: #dc3545; font-weight: bold;")
        status_layout.addWidget(self.status_light)
        status_layout.addWidget(self.status_text)
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # Server address
        address_label = QLabel(f"📡 {self.config.ip}:{self.config.port}")
        address_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(address_label)
        
        group.setLayout(layout)
        self._style_group_box(group)
        return group
    
    def _create_folder_section(self):
        """Create RIP folder selection section"""
        group = QGroupBox("RIP Folder Selection")
        layout = QVBoxLayout()
        
        self.folder_edit = QLineEdit()
        self.folder_edit.setText(self.config.rip_folder)
        self.folder_edit.setPlaceholderText("Select RIP folder containing .bmp files...")
        self.folder_edit.textChanged.connect(lambda text: setattr(self.config, 'rip_folder', text))
        
        browse_btn = QPushButton("Browse Folder")
        browse_btn.clicked.connect(self._browse_folder)
        
        layout.addWidget(self.folder_edit)
        layout.addWidget(browse_btn)
        
        group.setLayout(layout)
        self._style_group_box(group)
        return group
    
    def _create_settings_section(self):
        """Create print settings section"""
        group = QGroupBox("Print Settings")
        layout = QVBoxLayout()
        layout.setSpacing(12)
        
        # Copies
        copies_layout = QVBoxLayout()
        copies_layout.addWidget(QLabel("Number of copies per file:"))
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 100)
        self.copies_spin.setValue(self.config.num_copies)
        self.copies_spin.valueChanged.connect(lambda val: setattr(self.config, 'num_copies', val))
        copies_layout.addWidget(self.copies_spin)
        layout.addLayout(copies_layout)
        
        # Pattern
        pattern_layout = QVBoxLayout()
        pattern_layout.addWidget(QLabel("File pattern:"))
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems(["*.bmp", "*.BMP", "*.*"])
        self.pattern_combo.setCurrentText(self.config.pattern)
        self.pattern_combo.currentTextChanged.connect(lambda text: setattr(self.config, 'pattern', text))
        pattern_layout.addWidget(self.pattern_combo)
        layout.addLayout(pattern_layout)
        
        # Recursive
        self.recursive_check = QCheckBox("Include subdirectories")
        self.recursive_check.setChecked(self.config.recursive)
        self.recursive_check.toggled.connect(lambda checked: setattr(self.config, 'recursive', checked))
        layout.addWidget(self.recursive_check)
        
        # Continuous mode
        self.continuous_check = QCheckBox("🔄 Continuous Mode (Monitor for new files)")
        self.continuous_check.setChecked(self.config.continuous_mode)
        self.continuous_check.toggled.connect(lambda checked: setattr(self.config, 'continuous_mode', checked))
        layout.addWidget(self.continuous_check)
        
        # Max wait time
        wait_layout = QVBoxLayout()
        wait_layout.addWidget(QLabel("Max wait time for new files (seconds):"))
        self.max_wait_spin = QSpinBox()
        self.max_wait_spin.setRange(30, 3600)
        self.max_wait_spin.setValue(self.config.max_wait_time)
        self.max_wait_spin.setSuffix(" sec")
        self.max_wait_spin.setEnabled(self.config.continuous_mode)
        self.max_wait_spin.valueChanged.connect(lambda val: setattr(self.config, 'max_wait_time', val))
        wait_layout.addWidget(self.max_wait_spin)
        layout.addLayout(wait_layout)
        
        # Now connect the continuous mode checkbox to enable/disable max wait time
        self.continuous_check.toggled.connect(self.max_wait_spin.setEnabled)
        
        group.setLayout(layout)
        self._style_group_box(group)
        return group
    
    def _create_page_selection_section(self):
        """Create page selection section"""
        group = QGroupBox("Page Selection")
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Mode radios (mutually exclusive)
        self.opt_all = QRadioButton("Print all pages")
        self.opt_range = QRadioButton("Print range")
        self.opt_odd = QRadioButton("Odd only")
        self.opt_even = QRadioButton("Even only")
        
        # Set initial mode
        mode = self.config.page_filter.get('mode', 'all')
        if mode == 'all':
            self.opt_all.setChecked(True)
        elif mode == 'range':
            self.opt_range.setChecked(True)
        elif mode == 'odd':
            self.opt_odd.setChecked(True)
        elif mode == 'even':
            self.opt_even.setChecked(True)
        
        # Button group for mutual exclusion
        self.page_mode_group = QButtonGroup(self)
        self.page_mode_group.addButton(self.opt_all)
        self.page_mode_group.addButton(self.opt_range)
        self.page_mode_group.addButton(self.opt_odd)
        self.page_mode_group.addButton(self.opt_even)
        
        # Range inputs
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("From"))
        self.range_from = QSpinBox()
        self.range_from.setRange(1, 1000000)
        self.range_from.setValue(self.config.page_filter.get('from', 1))
        range_layout.addWidget(self.range_from)
        range_layout.addWidget(QLabel("to"))
        self.range_to = QSpinBox()
        self.range_to.setRange(1, 1000000)
        self.range_to.setValue(self.config.page_filter.get('to', 1000000))
        range_layout.addWidget(self.range_to)
        
        # Reverse checkbox (independent)
        self.reverse_check = QCheckBox("Reverse order")
        self.reverse_check.setChecked(self.config.page_filter.get('reverse', False))
        
        # Add to layout
        layout.addWidget(self.opt_all)
        layout.addWidget(self.opt_range)
        layout.addLayout(range_layout)
        
        odd_even_layout = QHBoxLayout()
        odd_even_layout.addWidget(self.opt_odd)
        odd_even_layout.addWidget(self.opt_even)
        layout.addLayout(odd_even_layout)
        
        layout.addWidget(self.reverse_check)
        
        # Enable/disable range inputs based on mode
        def update_range_state():
            enabled = self.opt_range.isChecked()
            self.range_from.setEnabled(enabled)
            self.range_to.setEnabled(enabled)
        
        self.opt_all.toggled.connect(update_range_state)
        self.opt_range.toggled.connect(update_range_state)
        self.opt_odd.toggled.connect(update_range_state)
        self.opt_even.toggled.connect(update_range_state)
        update_range_state()
        
        group.setLayout(layout)
        self._style_group_box(group)
        return group
    
    def _create_progress_section(self):
        """Create progress section"""
        group = QGroupBox("Progress")
        layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        self.progress_label = QLabel("Ready to start printing")
        self.progress_label.setStyleSheet("color: #6c757d; font-style: italic;")
        
        self.file_count_label = QLabel("Files to print: 0")
        self.file_count_label.setStyleSheet("font-weight: bold; color: #007bff;")
        
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.file_count_label)
        
        group.setLayout(layout)
        self._style_group_box(group)
        return group
    
    def _create_actions_section(self):
        """Create action buttons section"""
        group = QGroupBox("Actions")
        layout = QVBoxLayout()
        
        self.start_btn = QPushButton("Start Printing")
        self.start_btn.clicked.connect(lambda: self.start_printing_requested.emit(self.server_id))
        
        self.stop_btn = QPushButton("🛑 STOP PRINT SERVER")
        self.stop_btn.setObjectName("StopButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(lambda: self.stop_printing_requested.emit(self.server_id))
        
        self.open_folder_btn = QPushButton("Open RIP Folder")
        self.open_folder_btn.clicked.connect(self._open_folder)
        
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.open_folder_btn)
        
        group.setLayout(layout)
        self._style_group_box(group)
        return group
    
    def _create_status_section(self):
        """Create status and log section"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Status log
        status_group = QGroupBox("Print Status")
        status_layout = QVBoxLayout()
        
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setPlaceholderText("Print status and progress will appear here...")
        
        status_layout.addWidget(self.status_log)
        status_group.setLayout(status_layout)
        self._style_group_box(status_group)
        layout.addWidget(status_group)
        
        # Server info
        info_group = QGroupBox("Server Information")
        info_layout = QVBoxLayout()
        
        self.server_info = QTextEdit()
        self.server_info.setReadOnly(True)
        self.server_info.setMaximumHeight(150)
        self.server_info.setPlaceholderText("Server connection status will appear here...")
        
        info_layout.addWidget(self.server_info)
        info_group.setLayout(info_layout)
        self._style_group_box(info_group)
        layout.addWidget(info_group)
        
        return widget
    
    def _style_group_box(self, group_box):
        """Apply consistent styling to group boxes"""
        group_box.setStyleSheet("""
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                margin-top: 1ex;
                font-weight: bold;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                background-color: #ffffff;
                color: #495057;
            }
        """)
    
    def _browse_folder(self):
        """Browse for RIP folder"""
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select RIP Folder", 
            self.folder_edit.text() or os.getcwd()
        )
        if folder:
            self.folder_edit.setText(folder)
    
    def _open_folder(self):
        """Open RIP folder in file explorer"""
        folder_path = self.folder_edit.text().strip()
        if folder_path and os.path.exists(folder_path):
            if os.name == 'nt':
                os.startfile(folder_path)
            elif os.sys.platform == 'darwin':
                os.system(f"open '{folder_path}'")
            else:
                os.system(f"xdg-open '{folder_path}'")
    
    # === Public methods for updating UI ===
    
    def set_connected(self, connected: bool, message: str = ""):
        """Update connection status"""
        if connected:
            self.status_light.setStyleSheet("color: #28a745; font-size: 16pt;")
            self.status_text.setText(message or "Connected")
            self.status_text.setStyleSheet("color: #28a745; font-weight: bold;")
        else:
            self.status_light.setStyleSheet("color: #dc3545; font-size: 16pt;")
            self.status_text.setText(message or "Not Connected")
            self.status_text.setStyleSheet("color: #dc3545; font-weight: bold;")
    
    def update_progress(self, processed: int, total: int, message: str):
        """Update progress display"""
        if total > 0:
            percent = int((processed / total) * 100)
            self.progress_bar.setValue(percent)
        self.progress_label.setText(message)
        timestamp = time.strftime("%H:%M:%S")
        self.status_log.append(f"[{timestamp}] {message}")
        
        # Auto-scroll to bottom
        scrollbar = self.status_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def set_file_count(self, count: int):
        """Update file count display"""
        self.file_count_label.setText(f"Files to print: {count}")
    
    def set_printing_active(self, active: bool):
        """Enable/disable controls during printing"""
        self.start_btn.setEnabled(not active)
        self.stop_btn.setEnabled(active)
        self.folder_edit.setEnabled(not active)
        self.copies_spin.setEnabled(not active)
        self.pattern_combo.setEnabled(not active)
        self.recursive_check.setEnabled(not active)
        self.continuous_check.setEnabled(not active)
        
        if active:
            self.config.status = "printing"
        else:
            self.config.status = "idle"
    
    def append_server_info(self, message: str):
        """Append message to server info"""
        timestamp = time.strftime("%H:%M:%S")
        self.server_info.append(f"[{timestamp}] {message}")
    
    def get_page_filter(self):
        """Get current page filter configuration"""
        mode = 'all'
        if self.opt_range.isChecked():
            mode = 'range'
        elif self.opt_odd.isChecked():
            mode = 'odd'
        elif self.opt_even.isChecked():
            mode = 'even'
        
        page_filter = {
            'mode': mode,
            'from': self.range_from.value(),
            'to': self.range_to.value(),
            'reverse': self.reverse_check.isChecked(),
            'odd': mode == 'odd',
            'even': mode == 'even'
        }
        
        # Update config
        self.config.page_filter = page_filter
        return page_filter

