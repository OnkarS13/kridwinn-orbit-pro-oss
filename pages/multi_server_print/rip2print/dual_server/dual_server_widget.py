import os
import logging
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QComboBox, QRadioButton, QSpinBox, QFileDialog, QProgressBar,
    QTextEdit, QCheckBox, QScrollArea
)
from .dual_server_worker import DualServerWorker
from .dual_server_worker_real import DualServerWorkerReal
from ..shared.live_status_widget import LiveStatusWidget


class DualServerWidget(QWidget):
    """Dual Server job submission UI for RIP2PRINT."""

    def __init__(self, server_manager=None, parent=None):
        super().__init__(parent)
        self.server_manager = server_manager

        main = QVBoxLayout(self)

        # Wrap content in a scroll area to avoid squeezing
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); content_layout = QVBoxLayout(content)

        # Server selection
        server_group = QGroupBox("Servers")
        sg = QHBoxLayout()
        sg.addWidget(QLabel("Server 1:"))
        self.server1_combo = QComboBox(); self.server1_combo.setToolTip("First target GIS print server")
        sg.addWidget(self.server1_combo)
        sg.addSpacing(20)
        sg.addWidget(QLabel("Server 2:"))
        self.server2_combo = QComboBox(); self.server2_combo.setToolTip("Second target GIS print server")
        sg.addWidget(self.server2_combo)
        
        # Batch size display
        self.batch_size_label = QLabel("Queue Batch: 10")
        self.batch_size_label.setStyleSheet("color: #6c757d; font-size: 9pt;")
        self.batch_size_label.setToolTip("Number of files sent to printer queue at once (configured in Admin Panel)")
        sg.addSpacing(20)
        sg.addWidget(self.batch_size_label)
        
        server_group.setLayout(sg)
        content_layout.addWidget(server_group)

        # Folders & same-folder toggle
        folder_group = QGroupBox("Folders")
        fg = QVBoxLayout()
        self.same_folder = QCheckBox("Use same folder for both servers (odd/even split)")
        self.same_folder.setToolTip("When enabled, odd pages go to Server 1 and even pages go to Server 2 from the same folder")
        fg.addWidget(self.same_folder)

        row1 = QHBoxLayout()
        self.folder1_label = QLabel("Folder 1:")
        row1.addWidget(self.folder1_label)
        self.folder1_edit = QLineEdit(); self.folder1_edit.setToolTip("Folder for Server 1 (or shared folder when odd/even split is enabled)")
        self.browse1_btn = QPushButton("Browse")
        self.browse1_btn.clicked.connect(lambda: self._browse(self.folder1_edit))
        row1.addWidget(self.folder1_edit)
        row1.addWidget(self.browse1_btn)
        self.folder1_layout = row1  # Store layout for adding refresh button later
        fg.addLayout(row1)

        row2 = QHBoxLayout()
        self.folder2_label = QLabel("Folder 2:")
        row2.addWidget(self.folder2_label)
        self.folder2_edit = QLineEdit(); self.folder2_edit.setToolTip("Folder for Server 2 (disabled when odd/even split is enabled)")
        self.folder2_edit.setPlaceholderText("(Not used when odd/even split is enabled)")
        self.browse2_btn = QPushButton("Browse")
        self.browse2_btn.clicked.connect(lambda: self._browse(self.folder2_edit))
        row2.addWidget(self.folder2_edit)
        row2.addWidget(self.browse2_btn)
        fg.addLayout(row2)

        folder_group.setLayout(fg)
        content_layout.addWidget(folder_group)

        # Files counts (pattern removed - auto-detects all .bmp/.tif/.tiff)
        files_group = QGroupBox("Files")
        fl = QHBoxLayout()
        self.count1 = QLabel("Server 1 files: 0")
        self.count2 = QLabel("Server 2 files: 0")
        self.count_total = QLabel("Total: 0")
        self.count_total.setToolTip("Auto-detects all .bmp, .tif, and .tiff files (case-insensitive)")
        fl.addWidget(self.count1)
        fl.addSpacing(10)
        fl.addWidget(self.count2)
        fl.addSpacing(10)
        fl.addWidget(self.count_total)
        fl.addStretch()
        files_group.setLayout(fl)
        content_layout.addWidget(files_group)

        # File Groups Summary Panel - Folder 1
        self.groups_summary_group_1 = QGroupBox("File Groups - Folder 1")
        self.groups_summary_group_1.setVisible(False)  # Hidden initially

        gsg1_layout = QVBoxLayout()

        # Summary header label
        self.groups_summary_label_1 = QLabel("No groups detected")
        self.groups_summary_label_1.setStyleSheet("color: #666; font-style: italic;")
        gsg1_layout.addWidget(self.groups_summary_label_1)

        # Groups list widget (scrollable if many groups)
        self.groups_list_widget_1 = QTextEdit()
        self.groups_list_widget_1.setReadOnly(True)
        self.groups_list_widget_1.setMaximumHeight(100)  # Compact, scrollable
        self.groups_list_widget_1.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 5px;
                font-family: monospace;
                font-size: 9pt;
            }
        """)
        gsg1_layout.addWidget(self.groups_list_widget_1)

        self.groups_summary_group_1.setLayout(gsg1_layout)
        content_layout.addWidget(self.groups_summary_group_1)

        # File Groups Summary Panel - Folder 2
        self.groups_summary_group_2 = QGroupBox("File Groups - Folder 2")
        self.groups_summary_group_2.setVisible(False)  # Hidden initially

        gsg2_layout = QVBoxLayout()

        # Summary header label
        self.groups_summary_label_2 = QLabel("No groups detected")
        self.groups_summary_label_2.setStyleSheet("color: #666; font-style: italic;")
        gsg2_layout.addWidget(self.groups_summary_label_2)

        # Groups list widget (scrollable if many groups)
        self.groups_list_widget_2 = QTextEdit()
        self.groups_list_widget_2.setReadOnly(True)
        self.groups_list_widget_2.setMaximumHeight(100)  # Compact, scrollable
        self.groups_list_widget_2.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 5px;
                font-family: monospace;
                font-size: 9pt;
            }
        """)
        gsg2_layout.addWidget(self.groups_list_widget_2)

        self.groups_summary_group_2.setLayout(gsg2_layout)
        content_layout.addWidget(self.groups_summary_group_2)

        # Copies & Collation
        copies_group = QGroupBox("Copies & Collation")
        cg = QHBoxLayout()
        cg.addWidget(QLabel("Copies:"))
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 100)
        self.copies_spin.setValue(1)
        self.copies_spin.setToolTip("Number of copies per page per collation rule")
        cg.addWidget(self.copies_spin)
        cg.addStretch()
        self.collate_type1 = QRadioButton("Collate Type 1 (range × copies)")
        self.collate_type2 = QRadioButton("Collate Type 2 (copies per page × range)")
        self.collate_type1.setToolTip("Print full range, then repeat for each copy on each server")
        self.collate_type2.setToolTip("Print each page N times before moving to next on each server")
        self.collate_type1.setChecked(True)
        cg.addWidget(self.collate_type1)
        cg.addWidget(self.collate_type2)
        copies_group.setLayout(cg)
        content_layout.addWidget(copies_group)

        # Page range & reverse (no continuous)
        range_group = QGroupBox("Page Range")
        rg = QHBoxLayout()
        self.range_all = QRadioButton("All pages")
        self.range_spec = QRadioButton("Specify range")
        self.range_all.setToolTip("Print all detected files on both servers")
        self.range_spec.setToolTip(
            "Specify page range:\n"
            "• Same folder mode: Range applies to source files, then split odd/even\n"
            "  Example: Range 1-100 → Files 1-100 are split → Odd to Server1, Even to Server2\n"
            "• Separate folders: Range applies to EACH folder independently\n"
            "  Example: Range 1-50 → Server1 prints files 1-50 from Folder1, Server2 prints files 1-50 from Folder2"
        )
        self.range_all.setChecked(True)
        rg.addWidget(self.range_all)
        rg.addWidget(self.range_spec)
        rg.addStretch()
        rg.addWidget(QLabel("From"))
        self.range_from = QSpinBox()
        self.range_from.setRange(1, 1_000_000)
        self.range_from.setValue(1)
        self.range_from.setToolTip(
            "Range start (1-based)\n"
            "• Same folder: Starting file from source before split\n"
            "• Separate: Starting file from EACH folder"
        )
        rg.addWidget(self.range_from)
        rg.addWidget(QLabel("to"))
        self.range_to = QSpinBox()
        self.range_to.setRange(1, 1_000_000)
        self.range_to.setValue(1)  # User must set the end range explicitly
        self.range_to.setToolTip(
            "Range end (1-based) - Set the last page\n"
            "• Same folder: Ending file from source, then split odd/even\n"
            "• Separate: Ending file from EACH folder independently"
        )
        self.range_to.setSpecialValueText("")  # Show empty when at minimum
        rg.addWidget(self.range_to)
        
        # Add help label that explains current range behavior
        self.range_help_label = QLabel()
        self.range_help_label.setStyleSheet("color: #6c757d; font-style: italic; font-size: 9pt;")
        self.range_help_label.setWordWrap(True)
        rg_help = QVBoxLayout()
        rg_help.addLayout(rg)
        rg_help.addWidget(self.range_help_label)
        range_group.setLayout(rg_help)
        content_layout.addWidget(range_group)

        order_group = QGroupBox("Order")
        og = QHBoxLayout()
        self.reverse_order = QRadioButton("Reverse Order"); self.reverse_order.setToolTip("Print in reverse sequence order on both servers")
        og.addWidget(self.reverse_order)
        og.addStretch()
        order_group.setLayout(og)
        content_layout.addWidget(order_group)

        # Progress and log per server
        prog_group = QGroupBox("Progress")
        pg = QHBoxLayout()
        # Server 1
        s1_box = QVBoxLayout()
        s1_box.addWidget(QLabel("Server 1"))
        self.pbar1 = QProgressBar(); self.pbar1.setValue(0)
        self.pbar1.setStyleSheet("QProgressBar { color: black; }")
        self.log1 = QTextEdit(); self.log1.setReadOnly(True)
        self.log1.setMinimumHeight(220)
        self.log1.setStyleSheet("font-size: 11pt;")
        s1_box.addWidget(self.pbar1)
        s1_box.addWidget(self.log1)
        # Server 2
        s2_box = QVBoxLayout()
        s2_box.addWidget(QLabel("Server 2"))
        self.pbar2 = QProgressBar(); self.pbar2.setValue(0)
        self.pbar2.setStyleSheet("QProgressBar { color: black; }")
        self.log2 = QTextEdit(); self.log2.setReadOnly(True)
        self.log2.setMinimumHeight(220)
        self.log2.setStyleSheet("font-size: 11pt;")
        s2_box.addWidget(self.pbar2)
        s2_box.addWidget(self.log2)
        pg.addLayout(s1_box)
        pg.addLayout(s2_box)
        pg.setStretch(0, 1)
        pg.setStretch(1, 1)
        prog_group.setLayout(pg)
        content_layout.addWidget(prog_group)

        # Live status (per server)
        live_group = QGroupBox("Live Status")
        lg = QHBoxLayout()
        # Server 1 live
        s1 = QVBoxLayout(); s1.addWidget(QLabel("Server 1"))
        self.live_status1 = LiveStatusWidget(); self.live_status1.setVisible(False)
        s1.addWidget(self.live_status1)
        # Server 2 live
        s2 = QVBoxLayout(); s2.addWidget(QLabel("Server 2"))
        self.live_status2 = LiveStatusWidget(); self.live_status2.setVisible(False)
        s2.addWidget(self.live_status2)
        lg.addLayout(s1); lg.addLayout(s2)
        live_group.setLayout(lg)
        content_layout.addWidget(live_group)

        # Actions
        actions = QHBoxLayout()
        self.start_btn = QPushButton("Start Printing"); self.start_btn.setToolTip("Begin dual-server printing with current configuration")
        self.stop_btn = QPushButton("Stop/Pause"); self.stop_btn.setToolTip("Stop or pause both servers' print jobs (can be resumed)")
        self.resume_btn = QPushButton("Resume"); self.resume_btn.setToolTip("Resume printing from where it was stopped")
        self.stop_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.resume_btn.setVisible(False)
        self.start_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.stop_btn.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
        self.resume_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold;")
        actions.addWidget(self.start_btn)
        actions.addWidget(self.stop_btn)
        actions.addWidget(self.resume_btn)
        content_layout.addLayout(actions)

        # Finalize scroll
        scroll.setWidget(content)
        main.addWidget(scroll, 1)

        # Signals
        self.same_folder.toggled.connect(self._toggle_folder2)
        self.folder1_edit.textChanged.connect(self._update_counts)
        self.folder2_edit.textChanged.connect(self._update_counts)
        self.range_all.toggled.connect(self._update_range_help)
        self.range_spec.toggled.connect(self._update_range_help)
        self.range_spec.toggled.connect(self._update_range_enabled_state)  # Update enabled state when radio changes
        self.range_from.valueChanged.connect(self._update_range_help)
        self.range_to.valueChanged.connect(self._update_range_help)
        self.same_folder.toggled.connect(self._update_range_help)

        self._populate_servers()
        # Live update when servers are added/updated/removed
        if self.server_manager is not None:
            try:
                self.server_manager.server_added.connect(lambda _sid: self._populate_servers())
                self.server_manager.server_updated.connect(lambda _sid: self._populate_servers())
                self.server_manager.server_removed.connect(lambda _sid: self._populate_servers())
            except Exception:
                pass
        
        # Initialize range input enabled state based on current radio button selection
        self._update_range_enabled_state()
        # Re-populate whenever entering the view (covers server changes)
        try:
            self.window().windowTitleChanged.connect(lambda _t=None: self._populate_servers())
        except Exception:
            pass
        # Enforce distinct selection across combos
        try:
            self.server1_combo.currentIndexChanged.connect(self._on_server1_changed)
            self.server2_combo.currentIndexChanged.connect(self._on_server2_changed)
        except Exception:
            pass
        self._toggle_folder2()
        self._update_counts()
        self._update_range_help()  # Initialize range help text

        # Wire actions
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.resume_btn.clicked.connect(self._resume)
        self._worker = None
        self._thread = None
        self._sent1 = 0
        self._sent2 = 0
        self._printed1 = 0
        self._printed2 = 0
        self._resume_state = None  # Store resume state from stopped worker
        self._threads_finishing = False  # Flag to track if threads are finishing
        self._print_job_files1 = []  # Track files for Server 1 logging
        self._print_job_files2 = []  # Track files for Server 2 logging
        self._print_job_copies = 1  # Track copies for logging
        self._batch_size = 10  # Default batch size
        self._resume_repeat_pages = 1  # Default pages to re-print on resume (overridden by admin settings)
        
        # Load and apply admin settings
        self._load_and_apply_admin_settings()
    
    def closeEvent(self, event):
        """Clean up threads when widget is closed"""
        if self._thread is not None and self._thread.isRunning():
            if self._worker:
                self._worker.cancel()
            self._thread.quit()
            self._thread.wait(3000)
        event.accept()

    def _populate_servers(self):
        if not self.server_manager:
            return
        # Preserve current selections
        cur1 = self.server1_combo.currentData()
        cur2 = self.server2_combo.currentData()
        self.server1_combo.clear(); self.server2_combo.clear()
        # cache all servers for rebuilds
        self._all_servers = []
        for sid, cfg in self.server_manager.get_all_servers().items():
            label = f"{cfg.name} ({cfg.ip}:{cfg.port})"
            self._all_servers.append((sid, label))
        # Add placeholder as the first entry
        placeholder = "Select server"
        self.server1_combo.addItem(placeholder, None)
        self.server2_combo.addItem(placeholder, None)
        for sid, label in self._all_servers:
            self.server1_combo.addItem(label, sid)
            self.server2_combo.addItem(label, sid)
        # Restore selections if still present
        if cur1 is not None:
            idx1 = self.server1_combo.findData(cur1)
            if idx1 >= 0:
                self.server1_combo.setCurrentIndex(idx1)
            else:
                self.server1_combo.setCurrentIndex(0)
        else:
            self.server1_combo.setCurrentIndex(0)
        if cur2 is not None:
            idx2 = self.server2_combo.findData(cur2)
            if idx2 >= 0:
                self.server2_combo.setCurrentIndex(idx2)
            else:
                self.server2_combo.setCurrentIndex(0)
        else:
            self.server2_combo.setCurrentIndex(0)
        # Finally enforce distinct selections
        self._enforce_distinct()

    def _on_server1_changed(self, _):
        self._rebuild_combo_excluding(self.server2_combo, exclude_sid=self.server1_combo.currentData())

    def _on_server2_changed(self, _):
        self._rebuild_combo_excluding(self.server1_combo, exclude_sid=self.server2_combo.currentData())

    def _rebuild_combo_excluding(self, combo, exclude_sid=None):
        if not hasattr(self, "_all_servers"):
            return
        current_sid = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        # Add placeholder
        combo.addItem("Select server", None)
        for sid, label in self._all_servers:
            if exclude_sid is not None and sid == exclude_sid:
                continue
            combo.addItem(label, sid)
        # restore previous selection if still allowed
        if current_sid is not None:
            idx = combo.findData(current_sid)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        # default to first if nothing selected
        if combo.currentIndex() < 0 and combo.count() > 0:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _enforce_distinct(self):
        sid1 = self.server1_combo.currentData()
        sid2 = self.server2_combo.currentData()
        self._rebuild_combo_excluding(self.server2_combo, exclude_sid=sid1)
        self._rebuild_combo_excluding(self.server1_combo, exclude_sid=sid2)

    def _toggle_folder2(self):
        same = self.same_folder.isChecked()
        # When using same folder (odd/even split), disable Folder 2 input
        self.folder2_edit.setEnabled(not same)
        
        # Update label text to be clearer
        if same:
            self.folder1_label.setText("Source Folder:")
            self.folder2_label.setText("Folder 2:")
            # Optionally clear Folder 2 to avoid confusion
            if self.folder2_edit.text().strip():
                # Keep the value but just disable it - user can see what was there
                pass
        else:
            self.folder1_label.setText("Folder 1:")
            self.folder2_label.setText("Folder 2:")
        
        # Also update the counts to show the split
        self._update_counts()

    def _browse(self, target: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", target.text() or os.getcwd())
        if folder:
            target.setText(folder)

    def _update_counts(self):
        c1 = self._count(self.folder1_edit.text().strip())
        
        if self.same_folder.isChecked():
            # When using same folder with odd/even split, calculate the actual split
            # Odd pages go to Server 1, Even pages go to Server 2
            total_files = c1
            odd_count = (total_files + 1) // 2  # Ceiling division for odd
            even_count = total_files // 2        # Floor division for even
            
            self.count1.setText(f"Server 1 files: {odd_count} (odd)")
            self.count2.setText(f"Server 2 files: {even_count} (even)")
            self.count_total.setText(f"Total: {total_files}")
            
            # Update range spinboxes maximum to match actual file count
            if total_files > 0:
                self.range_from.setMaximum(total_files)
                self.range_to.setMaximum(total_files)
                # Update tooltips to show the valid range
                self.range_from.setToolTip(f"Range start index (1-based) - Max: {total_files}")
                self.range_to.setToolTip(f"Range end index (1-based) - Max: {total_files} - Set this to the last page you want to print")
                # Auto-populate "To" field with total file count (F.b fix)
                # Always set to file count to auto-populate the range
                self.range_to.setValue(total_files)
                # If "From" value exceeds count, adjust it
                if self.range_from.value() > total_files:
                    self.range_from.setValue(1)
            else:
                # Reset to default if no files
                self.range_from.setMaximum(1_000_000)
                self.range_to.setMaximum(1_000_000)
                self.range_from.setToolTip("Range start index (1-based)")
                self.range_to.setToolTip("Range end index (1-based) - Set this to the last page you want to print")
        else:
            # Separate folders - count each independently
            c2 = self._count(self.folder2_edit.text().strip())
            self.count1.setText(f"Server 1 files: {c1}")
            self.count2.setText(f"Server 2 files: {c2}")
            self.count_total.setText(f"Total: {c1 + c2}")
            
            # For separate folders, limit to the total of both folders
            total_files = c1 + c2
            if total_files > 0:
                self.range_from.setMaximum(total_files)
                self.range_to.setMaximum(total_files)
                # Update tooltips to show the valid range
                self.range_from.setToolTip(f"Range start index (1-based) - Max: {total_files}")
                self.range_to.setToolTip(f"Range end index (1-based) - Max: {total_files} - Set this to the last page you want to print")
                # Auto-populate "To" field with total file count (F.b fix)
                # Always set to file count to auto-populate the range
                self.range_to.setValue(total_files)
                # If "From" value exceeds count, adjust it
                if self.range_from.value() > total_files:
                    self.range_from.setValue(1)
            else:
                # Reset to default if no files
                self.range_from.setMaximum(1_000_000)
                self.range_to.setMaximum(1_000_000)
                self.range_from.setToolTip("Range start index (1-based)")
                self.range_to.setToolTip("Range end index (1-based) - Set this to the last page you want to print")

        # Trigger group detection to update File Groups panels
        # In Same Folder mode, only detect for Folder 1
        # In Separate Folders mode, detect for both folders
        if self.same_folder.isChecked():
            self._detect_and_display_groups_folder1()
            # Hide Folder 2 panel in Same Folder mode
            self.groups_summary_group_2.setVisible(False)
        else:
            self._detect_and_display_groups_folder1()
            self._detect_and_display_groups_folder2()

    def _count(self, folder: str) -> int:
        try:
            p = Path(folder)
            if p.is_dir():
                # Count all .bmp, .tif, .tiff files (case-insensitive, deduplicated)
                patterns = ['*.bmp', '*.BMP', '*.tif', '*.TIF', '*.tiff', '*.TIFF']
                files_set = set()
                for pat in patterns:
                    for f in p.glob(pat):
                        files_set.add(str(f))  # Keep original case for deduplication

                # Convert to list and deduplicate color planes to get actual page count
                files_list = list(files_set)
                files_list = self._deduplicate_color_planes(files_list)
                return len(files_list)  # Now counts pages, not individual files
        except Exception:
            return 0
        return 0

    def _detect_and_display_groups_folder1(self):
        """Detect file groups for Folder 1 and update summary panel"""
        try:
            # Get current folder
            folder_path = self.folder1_edit.text().strip()
            if not folder_path or not Path(folder_path).exists():
                self.groups_summary_group_1.setVisible(False)
                return

            # Load files from folder
            folder = Path(folder_path)
            patterns = ['*.bmp', '*.BMP', '*.tif', '*.TIF', '*.tiff', '*.TIFF']
            files_set = set()
            for pat in patterns:
                for f in folder.glob(pat):
                    files_set.add(str(f))

            files_list = list(files_set)
            if not files_list:
                self.groups_summary_group_1.setVisible(False)
                return

            # Check if grouping is enabled
            from ...shared.admin_config import AdminConfigManager
            config_manager = AdminConfigManager()
            settings = config_manager.load_settings()

            if not settings.enable_file_grouping:
                self.groups_summary_group_1.setVisible(False)
                return

            # Deduplicate color planes
            files_list = self._deduplicate_color_planes(files_list)

            # Convert to Path objects for grouping
            files = [Path(f) for f in files_list]

            # Group files
            from ..shared.file_grouping import group_files
            groups = group_files(files)

            if not groups:
                self.groups_summary_group_1.setVisible(False)
                return

            # Update UI
            self._update_groups_summary(groups, panel=1)

        except Exception as e:
            logging.error(f"Error detecting groups for Folder 1: {e}")
            self.groups_summary_group_1.setVisible(False)

    def _detect_and_display_groups_folder2(self):
        """Detect file groups for Folder 2 and update summary panel"""
        try:
            # Get current folder
            folder_path = self.folder2_edit.text().strip()
            if not folder_path or not Path(folder_path).exists():
                self.groups_summary_group_2.setVisible(False)
                return

            # Load files from folder
            folder = Path(folder_path)
            patterns = ['*.bmp', '*.BMP', '*.tif', '*.TIF', '*.tiff', '*.TIFF']
            files_set = set()
            for pat in patterns:
                for f in folder.glob(pat):
                    files_set.add(str(f))

            files_list = list(files_set)
            if not files_list:
                self.groups_summary_group_2.setVisible(False)
                return

            # Check if grouping is enabled
            from ...shared.admin_config import AdminConfigManager
            config_manager = AdminConfigManager()
            settings = config_manager.load_settings()

            if not settings.enable_file_grouping:
                self.groups_summary_group_2.setVisible(False)
                return

            # Deduplicate color planes
            files_list = self._deduplicate_color_planes(files_list)

            # Convert to Path objects for grouping
            files = [Path(f) for f in files_list]

            # Group files
            from ..shared.file_grouping import group_files
            groups = group_files(files)

            if not groups:
                self.groups_summary_group_2.setVisible(False)
                return

            # Update UI
            self._update_groups_summary(groups, panel=2)

        except Exception as e:
            logging.error(f"Error detecting groups for Folder 2: {e}")
            self.groups_summary_group_2.setVisible(False)

    def _update_groups_summary(self, groups, panel):
        """Update the groups summary panel with detected groups

        Args:
            groups: Dictionary of group name to files
            panel: 1 for Folder 1, 2 for Folder 2
        """
        if not groups:
            if panel == 1:
                self.groups_summary_group_1.setVisible(False)
            else:
                self.groups_summary_group_2.setVisible(False)
            return

        # Select the correct widgets based on panel
        if panel == 1:
            summary_label = self.groups_summary_label_1
            list_widget = self.groups_list_widget_1
            summary_group = self.groups_summary_group_1
        else:
            summary_label = self.groups_summary_label_2
            list_widget = self.groups_list_widget_2
            summary_group = self.groups_summary_group_2

        # Calculate totals
        total_groups = len(groups)
        total_files = sum(len(files) for files in groups.values())

        # Update summary header
        summary_label.setText(
            f"📊 {total_groups} group{'' if total_groups == 1 else 's'}, "
            f"{total_files} total file{'' if total_files == 1 else 's'}"
        )
        summary_label.setStyleSheet("color: #28a745; font-weight: bold;")

        # Build groups list text
        groups_text = ""
        for group_name, files in sorted(groups.items()):
            page_count = len(files)
            groups_text += f"• {group_name:<30} [{page_count:>3} pages]\n"

        list_widget.setPlainText(groups_text.strip())

        # Show the panel
        summary_group.setVisible(True)

    def _update_range_enabled_state(self):
        """Update the enabled state of range input boxes based on radio button selection."""
        # Only enable range inputs when "Specify range" is selected AND not currently printing
        is_printing = not self.start_btn.isEnabled()
        range_enabled = self.range_spec.isChecked() and not is_printing
        self.range_from.setEnabled(range_enabled)
        self.range_to.setEnabled(range_enabled)
    
    def _update_range_help(self):
        """Update the range help label based on current settings"""
        if self.range_all.isChecked():
            self.range_help_label.setText("ℹ️ All files mode: Both servers will print all detected files")
        else:
            r_from = self.range_from.value()
            r_to = self.range_to.value()
            same = self.same_folder.isChecked()
            
            if same:
                # Same folder - odd/even split
                if r_from == 1 and r_to == 1:
                    self.range_help_label.setText(
                        "⚠️ Range 1-1: Only file #1 will be selected, then split (odd→S1, even→S2)"
                    )
                else:
                    total_in_range = max(0, r_to - r_from + 1)
                    odd_count = (total_in_range + 1) // 2
                    even_count = total_in_range // 2
                    self.range_help_label.setText(
                        f"ℹ️ Same folder mode: Files {r_from}-{r_to} ({total_in_range} files) → "
                        f"Server 1 gets {odd_count} odd files, Server 2 gets {even_count} even files"
                    )
            else:
                # Separate folders
                if r_from == 1 and r_to == 1:
                    self.range_help_label.setText(
                        "⚠️ Range 1-1: Only file #1 from EACH folder will be printed"
                    )
                else:
                    self.range_help_label.setText(
                        f"ℹ️ Separate folders mode: Server 1 prints files {r_from}-{r_to} from Folder 1, "
                        f"Server 2 prints files {r_from}-{r_to} from Folder 2"
                    )

    def _get_global_settings(self) -> dict:
        """Collect global settings from main panel to pass as defaults to FileGroupSelector"""
        range_mode_all = self.range_all.isChecked()
        return {
            'copies': self.copies_spin.value(),
            'collate_type': 1 if self.collate_type1.isChecked() else 2,
            'reverse': self.reverse_order.isChecked(),
            'range_mode': 'all' if range_mode_all else 'range',
            'range_from': self.range_from.value(),
            'range_to': self.range_to.value(),
        }

    def _start(self):
        same = self.same_folder.isChecked()
        folder1 = self.folder1_edit.text().strip()
        folder2 = self.folder2_edit.text().strip()
        pattern = "*.bmp"  # Ignored by worker, kept for compatibility
        copies = self.copies_spin.value()
        collate_type = 1 if self.collate_type1.isChecked() else 2
        range_mode_all = self.range_all.isChecked()
        r_from = self.range_from.value()
        r_to = self.range_to.value()
        reverse = self.reverse_order.isChecked()

        # Initialize per-group variables (will be populated if file grouping is enabled and used)
        group_settings1 = None
        print_order1 = None
        group_settings2 = None
        print_order2 = None

        # Pre-validations
        if copies < 1:
            self.log1.append("Copies must be at least 1.")
            return
        if not range_mode_all:
            if r_from == 1 and r_to == 1:
                self.log1.append("⚠️ Warning: Range is set to print only page 1. If you want to print more pages, please adjust the 'to' value.")
                # Allow it to continue - user might actually want to print just page 1
            low = max(1, min(r_from, r_to))
            high = max(r_from, r_to)
            if low > high:
                self.log1.append("Invalid page range: From must be <= To.")
                return

        # Resolve selected servers
        sid1 = self.server1_combo.currentData()
        sid2 = self.server2_combo.currentData()
        cfg1 = self._get_server_by_id(sid1)
        cfg2 = self._get_server_by_id(sid2)
        # Validations
        if not cfg1 or not cfg2:
            self.log1.append("Select both servers before starting.")
            return
        if sid1 == sid2:
            self.log1.append("Select two different servers for Dual printing.")
            return
        if not folder1 or not Path(folder1).is_dir():
            self.log1.append("Select a valid Folder 1.")
            return
        if not same and (not folder2 or not Path(folder2).is_dir()):
            self.log2.append("Select a valid Folder 2.")
            return
        
        # Check for any RIP files (all extensions, deduplicated)
        patterns = ['*.bmp', '*.BMP', '*.tif', '*.TIF', '*.tiff', '*.TIFF']
        files1_set = set()
        for pat in patterns:
            for f in Path(folder1).glob(pat):
                # Store original path (not lowercase) for proper file operations
                files1_set.add(str(f.absolute()))
        
        # Deduplicate folder1 files by lowercase comparison but keep original paths
        unique_files1 = {}
        for f in files1_set:
            key = f.lower()
            if key not in unique_files1:
                unique_files1[key] = f
        files1_set = set(unique_files1.values())
        
        # Apply natural sorting for proper alphanumeric order (1, 2, 3... 10, 11, 12)
        import re
        def natural_sort_key(path):
            """Extract filename and split into text/number parts for natural sorting"""
            filename = Path(path).name
            return [int(text) if text.isdigit() else text.lower() 
                    for text in re.split(r'(\d+)', filename)]
        
        files1_list = sorted(list(files1_set), key=natural_sort_key)
        
        # Deduplicate color plane files before grouping
        files1_list = self._deduplicate_color_planes(files1_list)
        
        # Check for multi-group scenario (Phase 8: File Grouping)
        from ...shared.admin_config import AdminConfigManager
        config_mgr = AdminConfigManager()
        settings = config_mgr.load_settings()
        
        if settings.enable_file_grouping:
            from ..shared.file_grouping import group_files
            from ..shared.file_group_selector import FileGroupSelector
            
            groups = group_files(files1_list)
            
            # If groups detected in same-folder mode, show selector (even for single group)
            if same and len(groups) >= 1:
                self.log1.append(f"Detected {len(groups)} file group(s) from PDF(s)")
                self.log1.append("ℹ️ Note: Using global settings for all groups")

                # Simplified mode: selection and ordering only, no per-group settings
                dialog = FileGroupSelector(
                    groups,
                    global_settings=None,  # Don't need defaults in simplified mode
                    enable_per_group_settings=False,  # Disable per-group settings for Same Folder mode
                    parent=self
                )
                if dialog.exec() != FileGroupSelector.Accepted:
                    self.log1.append("Print job cancelled by user")
                    return  # User cancelled

                # Get selected files in user's chosen order
                files1_list = dialog.get_selected_files()
                selected_groups = len(dialog.get_selected_groups())
                total_pages = len(files1_list)  # Simple count in simplified mode

                self.log1.append(f"Selected {selected_groups} group(s), {total_pages} pages")

        if same:
            # Same folder mode - files2_list should be None (splitting is done in worker)
            files2_list = None

            if not files1_set:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "No Files Found",
                    "No RIP files found in the selected folder.\n\nPlease select a folder containing .bmp, .tif, or .tiff files."
                )
                return
        else:
            files2_set = set()
            for pat in patterns:
                for f in Path(folder2).glob(pat):
                    # Store original path (not lowercase) for proper file operations
                    files2_set.add(str(f.absolute()))
            
            # Deduplicate folder2 files by lowercase comparison but keep original paths
            unique_files2 = {}
            for f in files2_set:
                key = f.lower()
                if key not in unique_files2:
                    unique_files2[key] = f
            files2_set = set(unique_files2.values())
            
            # Apply natural sorting to files2 as well
            files2_list = sorted(list(files2_set), key=natural_sort_key)
            
            # Deduplicate color plane files before grouping
            files2_list = self._deduplicate_color_planes(files2_list)

            # Check for multi-group scenario in separate folders mode (Phase 8)
            if settings.enable_file_grouping:
                # Collect global settings to pass as defaults
                global_settings = self._get_global_settings()

                # Check Folder 1 for groups (even single group)
                groups1 = group_files(files1_list)
                if len(groups1) >= 1:
                    self.log1.append(f"Folder 1: Detected {len(groups1)} file group(s)")

                    # Per-group mode enabled for Separate Folders
                    dialog1 = FileGroupSelector(
                        groups1,
                        global_settings=global_settings,
                        enable_per_group_settings=True,  # Enable per-group for Separate Folders mode
                        parent=self
                    )
                    dialog1.setWindowTitle("File Groups - Folder 1 (Server 1)")
                    if dialog1.exec() != FileGroupSelector.Accepted:
                        self.log1.append("Print job cancelled by user")
                        return

                    # Extract per-group settings and print order
                    group_settings1 = dialog1.get_group_settings()
                    print_order1 = dialog1.get_print_order()
                    files1_list = dialog1.get_selected_files()

                    self.log1.append(f"✓ Server 1: {len(print_order1)} group(s), per-group settings configured")

                # Check Folder 2 for groups (even single group)
                groups2 = group_files(files2_list)
                if len(groups2) >= 1:
                    self.log2.append(f"Folder 2: Detected {len(groups2)} file group(s)")

                    # Per-group mode enabled for Separate Folders
                    dialog2 = FileGroupSelector(
                        groups2,
                        global_settings=global_settings,
                        enable_per_group_settings=True,  # Enable per-group for Separate Folders mode
                        parent=self
                    )
                    dialog2.setWindowTitle("File Groups - Folder 2 (Server 2)")
                    if dialog2.exec() != FileGroupSelector.Accepted:
                        self.log2.append("Print job cancelled by user")
                        return

                    # Extract per-group settings and print order
                    group_settings2 = dialog2.get_group_settings()
                    print_order2 = dialog2.get_print_order()
                    files2_list = dialog2.get_selected_files()

                    self.log2.append(f"✓ Server 2: {len(print_order2)} group(s), per-group settings configured")
            
            # Check if both folders are empty
            if not files1_set and not files2_set:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "No Files Found",
                    "No RIP files found in either folder.\n\nPlease select folders containing .bmp, .tif, or .tiff files."
                )
                return
            
            # Check if only one folder has files - ask user if they want to continue
            if not files1_set or not files2_set:
                from PySide6.QtWidgets import QMessageBox
                
                if not files1_set:
                    empty_folder = "Folder 1"
                    has_files_folder = "Folder 2"
                    file_count = len(files2_set)
                else:
                    empty_folder = "Folder 2"
                    has_files_folder = "Folder 1"
                    file_count = len(files1_set)
                
                reply = QMessageBox.question(
                    self,
                    "One Folder Empty",
                    f"{empty_folder} does not contain any RIP files.\n\n"
                    f"{has_files_folder} has {file_count} file(s).\n\n"
                    f"Do you want to continue printing with only {has_files_folder}?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply != QMessageBox.Yes:
                    return  # User cancelled
        
        ip1 = cfg1.ip; port1 = cfg1.port
        ip2 = cfg2.ip; port2 = cfg2.port

        # Clean up previous thread if it exists
        if self._thread is not None and self._thread.isRunning():
            self.log1.append("Waiting for previous job to finish...")
            self._thread.quit()
            self._thread.wait(3000)  # Wait max 3 seconds
        
        # Clear any previous resume state when starting a new job
        self._resume_state = None
        self.resume_btn.setVisible(False)
        self.resume_btn.setEnabled(False)
        

        # Apply page range filter to get actual files that will be printed
        # This ensures database only records files that are actually printed
        if not range_mode_all:
            # Apply the same range logic as the worker
            low = max(1, min(r_from, r_to))
            high = max(r_from, r_to)

            if same:
                # Same folder mode: apply range first, then split odd/even
                files1_filtered = [f for idx, f in enumerate(files1_list, start=1) if low <= idx <= high]
                self._print_job_files1 = [files1_filtered[i] for i in range(0, len(files1_filtered), 2)]  # Odd indices
                self._print_job_files2 = [files1_filtered[i] for i in range(1, len(files1_filtered), 2)]  # Even indices
            else:
                # Separate folders mode: apply range to each folder independently
                self._print_job_files1 = [f for idx, f in enumerate(files1_list, start=1) if low <= idx <= high]
                self._print_job_files2 = [f for idx, f in enumerate(files2_list, start=1) if low <= idx <= high]
        else:
            # All pages mode: track all files
            if same:
                # Same folder mode: split files odd/even for logging
                self._print_job_files1 = [files1_list[i] for i in range(0, len(files1_list), 2)]  # Odd indices
                self._print_job_files2 = [files1_list[i] for i in range(1, len(files1_list), 2)]  # Even indices
            else:
                # Separate folders mode: track each folder separately
                self._print_job_files1 = files1_list
                self._print_job_files2 = files2_list

        self._print_job_copies = copies

        # Check for reprints if detection is enabled (check all files from both servers)
        all_files_to_check = self._print_job_files1 + self._print_job_files2
        if not self._check_reprint_detection(all_files_to_check):
            return  # User cancelled or reprint blocked

        # SMART BATCH SIZE ANALYZER - Analyze folder and recommend optimal batch size
        from pages.rip_to_print.rip_to_print import GISPrintServerClient, RIPFolderPrinter, show_batch_size_recommendation_dialog

        try:
            # Create temporary client and printer for analysis (use folder1 as primary, no connection needed)
            temp_client = GISPrintServerClient(host=ip1, port=port1)
            temp_printer = RIPFolderPrinter(
                client=temp_client,
                progress_callback=None,
                batch_size=self._batch_size
            )

            # Analyze folder and get recommendation
            analysis = temp_printer.analyze_folder_and_recommend_batch_size(
                folder_path=folder1,
                pattern="*.bmp",
                recursive=False,
                current_batch_size=self._batch_size
            )

            # Show recommendation dialog and get user choice
            user_choice = show_batch_size_recommendation_dialog(self, analysis)

            if user_choice == 'cancel':
                self.log1.append("❌ Print cancelled by user")
                self.log2.append("❌ Print cancelled by user")
                return  # User cancelled
            elif user_choice == 'recommended':
                # User wants to use recommended batch size
                recommended_batch = analysis.get('recommended_batch_size', self._batch_size)
                self.log1.append(f"✅ Using recommended batch size: {recommended_batch} pages")
                self.log1.append(f"   (Previous: {self._batch_size} pages)")
                self.log2.append(f"✅ Using recommended batch size: {recommended_batch} pages")
                self.log2.append(f"   (Previous: {self._batch_size} pages)")
                self._batch_size = recommended_batch  # Update for this print job
            else:  # 'continue'
                self.log1.append(f"ℹ️ Continuing with current batch size: {self._batch_size} pages")
                self.log2.append(f"ℹ️ Continuing with current batch size: {self._batch_size} pages")

        except Exception as e:
            # If analyzer fails, just log and continue with current settings
            logger = logging.getLogger(__name__)
            logger.warning(f"Batch size analyzer failed: {e}")
            self.log1.append(f"⚠️ Batch analyzer warning: {e}")
            self.log1.append(f"ℹ️ Continuing with batch size: {self._batch_size}")
            self.log2.append(f"⚠️ Batch analyzer warning: {e}")
            self.log2.append(f"ℹ️ Continuing with batch size: {self._batch_size}")

        # Instantiate real dual worker with per-group settings
        self._worker = DualServerWorkerReal(
            ip1, port1, ip2, port2, same, folder1, folder2, pattern, copies,
            collate_type, range_mode_all, r_from, r_to, reverse,
            resume_server1_from=0, resume_server2_from=0,
            files1_list=files1_list, files2_list=files2_list,  # Pass filtered lists
            batch_size=self._batch_size,
            repeat_resume_pages=self._resume_repeat_pages,
            group_settings1=group_settings1,  # Per-group settings for Server 1 (or None)
            print_order1=print_order1,        # Print order for Server 1 (or None)
            group_settings2=group_settings2,  # Per-group settings for Server 2 (or None)
            print_order2=print_order2,        # Print order for Server 2 (or None)
        )

        from PySide6.QtCore import QThread
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        
        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        if hasattr(self._worker, 'status_update'):
            self._worker.status_update.connect(self._on_status)
        if hasattr(self._worker, 'error_occurred'):
            self._worker.error_occurred.connect(self._on_error_detail)
        if hasattr(self._worker, 'server_error_detected'):
            self._worker.server_error_detected.connect(self._on_server_error)
        
        # Proper cleanup when finished
        # Note: Don't use deleteLater directly - handle cleanup in _on_finished
        self._worker.finished.connect(self._thread.quit)
        
        self._set_printing_state(True)
        self.log1.clear(); self.log2.clear()
        self.pbar1.setValue(0); self.pbar2.setValue(0)
        self.pbar1.setStyleSheet("QProgressBar { color: black; }")  # Reset progress bar styles
        self.pbar2.setStyleSheet("QProgressBar { color: black; }")
        self._sent1 = self._sent2 = self._printed1 = self._printed2 = 0
        # Reset live status widgets (they handle their own display)
        self.live_status1.clear_error()  # Clear any previous error states
        self.live_status2.clear_error()
        self.live_status1.update_status(0, 0, 0, None)
        self.live_status2.update_status(0, 0, 0, None)
        self._thread.start()
        self.live_status1.setVisible(True)
        self.live_status2.setVisible(True)

    def _stop(self):
        if self._worker:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                'Stop Printing',
                'Are you sure you want to stop printing on both servers?\n\nYou can resume it later from where it stopped.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            
            # Update UI state immediately to give user feedback
            self._set_printing_state(False)
            self.log1.append("Stopping servers...")
            self.log2.append("Stopping servers...")
            
            try:
                self._worker.cancel()
                # Mark that threads are finishing
                self._threads_finishing = True
                
                # Save resume state from worker immediately
                if hasattr(self._worker, 'resume_state') and self._worker.resume_state:
                    self._resume_state = self._worker.resume_state
                    s1_printed = self._resume_state.get('server1_last_printed', 0)
                    s1_total = self._resume_state.get('server1_total', 0)
                    s2_printed = self._resume_state.get('server2_last_printed', 0)
                    s2_total = self._resume_state.get('server2_total', 0)
                    self.log1.append(f"Server 1 stopped. Printed {s1_printed}/{s1_total} pages.")
                    self.log2.append(f"Server 2 stopped. Printed {s2_printed}/{s2_total} pages.")
                    # Show resume button but disable it until threads finish
                    self.resume_btn.setVisible(True)
                    self.resume_btn.setEnabled(False)
                    self.resume_btn.setText("Resume (waiting for threads to be cleared...)")
                else:
                    self.log1.append("Cancelling print jobs...")
                    self.log2.append("Cancelling print jobs...")
            except Exception as e:
                self.log1.append(f"Stop error: {e}")
            
            # DON'T wait synchronously - let the thread finish naturally
            # The _on_finished callback will re-enable the resume button
            self.log1.append("Print job will stop after current operation completes...")
            self.log2.append("Print job will stop after current operation completes...")

    def _resume(self):
        """Resume printing from where it was stopped"""
        if not self._resume_state:
            self.log1.append("No resume state available.")
            return
        
        # Safety check - should not happen if button is disabled correctly
        if self._threads_finishing:
            self.log1.append("⚠️ Please wait for threads to finish...")
            return
        
        # At this point, _on_finished has already cleaned up the old thread
        # Just verify it's clean
        if self._thread is not None or self._worker is not None:
            self.log1.append("⚠️ Warning: Old thread/worker still exists, cleaning up...")
            try:
                if self._worker is not None:
                    self._worker.deleteLater()
                    self._worker = None
                if self._thread is not None:
                    self._thread.deleteLater()
                    self._thread = None
                # Small delay
                from PySide6.QtCore import QThread
                QThread.msleep(200)
            except Exception as e:
                self.log1.append(f"Cleanup warning: {e}")
        
        # Validate resume state
        same_folder = self._resume_state.get('same_folder', False)
        folder1 = self._resume_state.get('folder1')
        folder2 = self._resume_state.get('folder2')
        
        if not folder1 or not Path(folder1).is_dir():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Resume Failed",
                f"Folder 1 not found: {folder1}\n\nCannot resume printing."
            )
            self._resume_state = None
            self.resume_btn.setVisible(False)
            return
        
        if not same_folder and (not folder2 or not Path(folder2).is_dir()):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Resume Failed",
                f"Folder 2 not found: {folder2}\n\nCannot resume printing."
            )
            self._resume_state = None
            self.resume_btn.setVisible(False)
            return
        
        s1_printed = self._resume_state.get('server1_last_printed', 0)
        s1_total = self._resume_state.get('server1_total', 0)
        s2_printed = self._resume_state.get('server2_last_printed', 0)
        s2_total = self._resume_state.get('server2_total', 0)
        
        if s1_printed >= s1_total and s2_printed >= s2_total:
            self.log1.append(f"Both servers already complete. Nothing to resume.")
            self._resume_state = None
            self.resume_btn.setVisible(False)
            return
        
        # Extract all settings from resume state
        ip1 = self._resume_state.get('server1_ip')
        port1 = self._resume_state.get('server1_port')
        ip2 = self._resume_state.get('server2_ip')
        port2 = self._resume_state.get('server2_port')
        pattern = self._resume_state.get('pattern', '*.bmp')
        copies = self._resume_state.get('copies', 1)
        collate_type = self._resume_state.get('collate_type', 1)
        range_mode_all = self._resume_state.get('range_mode_all', True)
        r_from = self._resume_state.get('range_from', 1)
        r_to = self._resume_state.get('range_to', 1)
        reverse = self._resume_state.get('reverse_order', False)
        batch_size = self._resume_state.get('batch_size', self._batch_size)
        files1_list = self._resume_state.get('files1_list', None)
        files2_list = self._resume_state.get('files2_list', None)

        # Extract per-group settings from resume state
        group_settings1 = self._resume_state.get('group_settings1', None)
        print_order1 = self._resume_state.get('print_order1', None)
        group_settings2 = self._resume_state.get('group_settings2', None)
        print_order2 = self._resume_state.get('print_order2', None)

        self.log1.append(f"Resuming Server 1 from page {s1_printed + 1}/{s1_total}...")
        self.log2.append(f"Resuming Server 2 from page {s2_printed + 1}/{s2_total}...")

        # Create new worker starting from the next page for each server
        self._worker = DualServerWorkerReal(
            ip1, port1, ip2, port2, same_folder, folder1, folder2, pattern, copies,
            collate_type, range_mode_all, r_from, r_to, reverse,
            resume_server1_from=s1_printed, resume_server2_from=s2_printed,
            files1_list=files1_list, files2_list=files2_list,
            batch_size=batch_size,
            repeat_resume_pages=self._resume_repeat_pages,
            group_settings1=group_settings1,  # Pass per-group settings for resume
            print_order1=print_order1,
            group_settings2=group_settings2,
            print_order2=print_order2,
        )
        
        from PySide6.QtCore import QThread
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        
        # Connect signals
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        if hasattr(self._worker, 'status_update'):
            self._worker.status_update.connect(self._on_status)
        if hasattr(self._worker, 'error_occurred'):
            self._worker.error_occurred.connect(self._on_error_detail)
        if hasattr(self._worker, 'server_error_detected'):
            self._worker.server_error_detected.connect(self._on_server_error)
        
        self._worker.finished.connect(self._thread.quit)
        
        # Hide resume button during printing
        self.resume_btn.setVisible(False)
        self.resume_btn.setEnabled(False)
        
        self._set_printing_state(True)
        self._thread.start()
        self.live_status1.setVisible(True)
        self.live_status2.setVisible(True)
    
    def _on_progress(self, server_tag: str, current: int, total: int, message: str):
        # Calculate percentage correctly, capping at 100%
        if total > 0:
            pct = min(100, int((current / total) * 100))
        else:
            pct = 0
            
        if server_tag == "server1":
            self.pbar1.setValue(pct)
            self.log1.append(message)
            # LiveStatusWidget handles display via _on_status method
        else:
            self.pbar2.setValue(pct)
            self.log2.append(message)
            # LiveStatusWidget handles display via _on_status method

    def _on_finished(self, success: bool):
        self._set_printing_state(False)
        self.log1.append("Done" if success else "Failed/Cancelled")
        self.log2.append("Done" if success else "Failed/Cancelled")
        
        # Give a small delay to ensure worker threads are completely done
        from PySide6.QtCore import QTimer
        
        def delayed_cleanup():
            # Properly clean up thread and worker references
            if self._thread is not None:
                try:
                    # Wait for thread to finish cleanly
                    if self._thread.isRunning():
                        self._thread.quit()
                        self._thread.wait(5000)  # Wait up to 5 seconds
                    
                    # Now safely delete objects
                    if self._worker is not None:
                        self._worker.deleteLater()
                    self._thread.deleteLater()
                except Exception as e:
                    self.log1.append(f"Cleanup warning: {e}")
            
            # Clear references to allow garbage collection
            self._worker = None
            self._thread = None
            
            # Mark threads as finished
            self._threads_finishing = False
            
            if success:
                # Clear resume state on successful completion
                self._resume_state = None
                self.resume_btn.setVisible(False)
                self.resume_btn.setEnabled(False)
                self.resume_btn.setText("Resume")
                
                # Record to history database FIRST (before clearing files list)
                self._record_to_history(self._print_job_files1, "Server1")
                self._record_to_history(self._print_job_files2, "Server2")
                
                # Execute post-print action on ONLY the printed files
                same_folder_mode = self.same_folder.isChecked()
                
                if same_folder_mode:
                    # Same folder mode - combine both file lists
                    all_printed_files = self._print_job_files1 + self._print_job_files2
                    if all_printed_files:
                        self._execute_post_print_action(all_printed_files)
                else:
                    # Separate folders mode - process each list separately
                    if self._print_job_files1:
                        self._execute_post_print_action(self._print_job_files1, use_dest_2=False)
                    if self._print_job_files2:
                        self._execute_post_print_action(self._print_job_files2, use_dest_2=True)
                
                # Log print job (this clears the files lists)
                self._log_print_job()
                
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Print Complete", "Dual-server job finished successfully.")
            else:
                # If failed/cancelled and we have resume state, enable the resume button
                if self._resume_state:
                    self.resume_btn.setEnabled(True)
                    self.resume_btn.setText("Resume")
                    self.log1.append("✓ Threads finished - Resume button is now ready")
                    self.log2.append("✓ Threads finished - Resume button is now ready")
        
        # Delay cleanup by 500ms to ensure internal threads are fully done
        QTimer.singleShot(500, delayed_cleanup)
        # keep live status visible

    def _on_status(self, tag: str, status: dict):
        total = status.get('total', 0)
        sent = status.get('sent', 0)
        printed = status.get('printed', 0)
        speed = status.get('speed')
        if tag == "server1":
            self.live_status1.update_status(sent, printed, total, speed)
        else:
            self.live_status2.update_status(sent, printed, total, speed)

    def _get_server_by_id(self, sid):
        if not self.server_manager:
            return None
        return self.server_manager.get_server(sid)

    def _on_error(self, msg: str):
        # Large, visible error message in red/bold
        self.log1.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ ERROR: {msg}</span>")
        self.log2.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ ERROR: {msg}</span>")
    
    def _on_error_detail(self, server_tag: str, error_info: dict):
        """Handle detailed per-server error with last known counts"""
        error_msg = error_info.get('error_msg', 'Unknown error')
        last_sent = error_info.get('sent', 0)
        last_printed = error_info.get('printed', 0)
        total = error_info.get('total', 0)
        
        # Determine which server(s) errored
        if server_tag == "server1" or server_tag == "both":
            # Show error in Server 1 live status widget
            self.live_status1.show_error(error_msg, last_sent, last_printed, total)
            # Turn Server 1 progress bar red
            self.pbar1.setStyleSheet("QProgressBar { color: black; } QProgressBar::chunk { background-color: #dc3545; }")
            # Add detailed error to Server 1 log
            self.log1.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")
            self.log1.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ SERVER 1 FAILED</span>")
            self.log1.append(f"<span style='color: #dc3545;'>Error: {error_msg}</span>")
            self.log1.append(f"<span style='color: #6c757d;'>Last known status:</span>")
            self.log1.append(f"<span style='color: #6c757d;'>  • Files Sent: {last_sent}/{total}</span>")
            self.log1.append(f"<span style='color: #6c757d;'>  • Files Printed: {last_printed}/{total}</span>")
            self.log1.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")
        
        if server_tag == "server2" or server_tag == "both":
            # Show error in Server 2 live status widget
            self.live_status2.show_error(error_msg, last_sent, last_printed, total)
            # Turn Server 2 progress bar red
            self.pbar2.setStyleSheet("QProgressBar { color: black; } QProgressBar::chunk { background-color: #dc3545; }")
            # Add detailed error to Server 2 log
            self.log2.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")
            self.log2.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ SERVER 2 FAILED</span>")
            self.log2.append(f"<span style='color: #dc3545;'>Error: {error_msg}</span>")
            self.log2.append(f"<span style='color: #6c757d;'>Last known status:</span>")
            self.log2.append(f"<span style='color: #6c757d;'>  • Files Sent: {last_sent}/{total}</span>")
            self.log2.append(f"<span style='color: #6c757d;'>  • Files Printed: {last_printed}/{total}</span>")
            self.log2.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")

    def _on_server_error(self, server_tag: str, error_details: dict):
        """Handle server error with auto-saved resume state and show popup"""
        error_type = error_details.get('error_type', 'UNKNOWN')
        error_msg = error_details.get('error_msg', 'Unknown server error')
        last_printed = error_details.get('last_printed', 0)
        total = error_details.get('total', 0)
        can_resume = error_details.get('can_resume', False)
        resume_from = error_details.get('resume_from', last_printed)

        # Update UI state
        self._set_printing_state(False)

        # Determine which server(s) errored
        server_name = {
            "server1": "Server 1",
            "server2": "Server 2",
            "both": "Both Servers"
        }.get(server_tag, server_tag)

        # Show error in live status widgets and logs
        if server_tag == "server1" or server_tag == "both":
            self.live_status1.show_error(f"{error_type}: {error_msg}", 0, last_printed, total)
            self.pbar1.setStyleSheet("QProgressBar { color: black; } QProgressBar::chunk { background-color: #dc3545; }")
            self.log1.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")
            self.log1.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ SERVER 1 ERROR DETECTED</span>")
            self.log1.append(f"<span style='color: #dc3545;'>Error Type: {error_type}</span>")
            self.log1.append(f"<span style='color: #dc3545;'>Error: {error_msg}</span>")
            self.log1.append(f"<span style='color: #6c757d;'>Last printed page: {last_printed}/{total}</span>")
            if can_resume:
                self.log1.append(f"<span style='color: #28a745; font-weight: bold;'>✅ Resume state saved automatically</span>")
                self.log1.append(f"<span style='color: #6c757d;'>Will resume from page: {resume_from}</span>")
            self.log1.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")

        if server_tag == "server2" or server_tag == "both":
            self.live_status2.show_error(f"{error_type}: {error_msg}", 0, last_printed, total)
            self.pbar2.setStyleSheet("QProgressBar { color: black; } QProgressBar::chunk { background-color: #dc3545; }")
            self.log2.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")
            self.log2.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ SERVER 2 ERROR DETECTED</span>")
            self.log2.append(f"<span style='color: #dc3545;'>Error Type: {error_type}</span>")
            self.log2.append(f"<span style='color: #dc3545;'>Error: {error_msg}</span>")
            self.log2.append(f"<span style='color: #6c757d;'>Last printed page: {last_printed}/{total}</span>")
            if can_resume:
                self.log2.append(f"<span style='color: #28a745; font-weight: bold;'>✅ Resume state saved automatically</span>")
                self.log2.append(f"<span style='color: #6c757d;'>Will resume from page: {resume_from}</span>")
            self.log2.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")

        # Save resume state from worker
        if hasattr(self._worker, 'resume_state') and self._worker.resume_state:
            self._resume_state = self._worker.resume_state

            # Show resume button
            if can_resume:
                self.resume_btn.setVisible(True)
                self.resume_btn.setEnabled(True)
                self.resume_btn.setText("Resume")

        # Show error popup dialog
        from PySide6.QtWidgets import QMessageBox
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(f"{server_name} Error Detected")

        if can_resume:
            msg_box.setText(f"<b>Print job stopped due to {server_name.lower()} error:</b><br><br>"
                           f"<span style='color: #dc3545;'>{error_type}</span><br>"
                           f"{error_msg}<br><br>"
                           f"<b>Progress:</b> {last_printed}/{total} pages printed<br><br>"
                           f"<span style='color: #28a745;'><b>✓ Resume state saved</b></span><br>"
                           f"Click <b>Resume</b> to continue from page {resume_from}")
            msg_box.setInformativeText("The print job has been automatically saved.\n"
                                      "You can resume printing by clicking the Resume button.")
        else:
            msg_box.setText(f"<b>Print job failed due to {server_name.lower()} error:</b><br><br>"
                           f"<span style='color: #dc3545;'>{error_type}</span><br>"
                           f"{error_msg}<br><br>"
                           f"<b>Progress:</b> {last_printed}/{total} pages printed")
            msg_box.setInformativeText("The print job cannot be resumed automatically.\n"
                                      "Please check the server status and try again.")

        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    def _set_printing_state(self, printing: bool):
        self.start_btn.setEnabled(not printing)
        self.stop_btn.setEnabled(printing)
        self.server1_combo.setEnabled(not printing)
        self.server2_combo.setEnabled(not printing)
        self.same_folder.setEnabled(not printing)
        self.folder1_edit.setEnabled(not printing)
        self.folder2_edit.setEnabled(not printing and not self.same_folder.isChecked())
        self.copies_spin.setEnabled(not printing)
        self.collate_type1.setEnabled(not printing)
        self.collate_type2.setEnabled(not printing)
        self.range_all.setEnabled(not printing)
        self.range_spec.setEnabled(not printing)
        # Use the helper method to update range input enabled state
        self._update_range_enabled_state()
    
    def _open_admin_panel(self):
        """Open admin panel with password authentication"""
        from ...shared.admin_auth import AdminAuthManager
        from ...shared.admin_password_setup_dialog import AdminPasswordSetupDialog
        from ...shared.admin_password_entry_dialog import AdminPasswordEntryDialog
        from ...shared.admin_settings_dialog import AdminSettingsDialog
        from PySide6.QtWidgets import QMessageBox, QDialog
        
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
                        "Admin password has been set successfully.\n\nYou can now access the admin panel."
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
        from ...shared.admin_settings_dialog import AdminSettingsDialog
        from PySide6.QtWidgets import QMessageBox, QDialog
        
        settings_dialog = AdminSettingsDialog(self)
        if settings_dialog.exec() == QDialog.Accepted:
            # Reload and apply settings after save
            self._load_and_apply_admin_settings()
    
    def _load_and_apply_admin_settings(self):
        """Load admin settings and apply to UI"""
        try:
            from ...shared.admin_config import AdminConfigManager
            from pathlib import Path
            
            config_manager = AdminConfigManager()
            settings = config_manager.load_settings()
            
            # Apply settings
            self._apply_fix_browse_folder(settings)
            self._apply_operator_controls(settings)
            
            # Apply batch size
            self._batch_size = settings.batch_size
            self.batch_size_label.setText(f"Queue Batch: {self._batch_size}")
            
            # Apply resume repeat pages (how many previous pages to re-print on resume)
            self._resume_repeat_pages = getattr(settings, "resume_repeat_pages", 1)
        except Exception as e:
            logging.error(f"Error loading admin settings: {e}")
    
    def _apply_fix_browse_folder(self, settings):
        """Apply fixed folder setting"""
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QMessageBox, QPushButton
        from pathlib import Path
        
        if settings.fix_browse_folder and settings.fixed_folder_path:
            # Validate folder 1 exists
            folder_path = Path(settings.fixed_folder_path)
            if not folder_path.exists() or not folder_path.is_dir():
                QMessageBox.warning(
                    self,
                    "Admin Settings Error",
                    f"Fixed folder path 1 does not exist:\\n{settings.fixed_folder_path}\\n\\n"
                    "Contact administrator to update the folder path."
                )
                return
            
            # Set the fixed folder for folder1
            self.folder1_edit.setText(settings.fixed_folder_path)
            self.folder1_edit.setReadOnly(True)
            self.folder1_edit.setStyleSheet("""
                QLineEdit {
                    background-color: #f8f9fa;
                    border: 1px dashed #6c757d;
                    color: #495057;
                }
            """)
            self.folder1_edit.setToolTip("Folder locked by administrator")
            
            # Hide browse button for folder1
            self.browse1_btn.setVisible(False)
            
            # Create/show refresh button for folder1
            if not hasattr(self, 'refresh1_btn'):
                self.refresh1_btn = QPushButton("🔄 Refresh")
                self.refresh1_btn.setToolTip("Refresh file list")
                self.refresh1_btn.clicked.connect(self._update_counts)
                self.refresh1_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #6c757d;
                        color: white;
                        font-weight: bold;
                        padding: 6px 12px;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background-color: #5a6268;
                    }
                """)
                self.folder1_layout.addWidget(self.refresh1_btn)
            else:
                self.refresh1_btn.setVisible(True)
            
            # Handle folder 2 if path is provided (for separate folders mode)
            if settings.fixed_folder_path_2:
                # Validate folder 2 exists
                folder2_path = Path(settings.fixed_folder_path_2)
                if folder2_path.exists() and folder2_path.is_dir():
                    # Lock folder 2
                    self.folder2_edit.setText(settings.fixed_folder_path_2)
                    self.folder2_edit.setReadOnly(True)
                    self.folder2_edit.setStyleSheet("""
                        QLineEdit {
                            background-color: #f8f9fa;
                            border: 1px dashed #6c757d;
                            color: #495057;
                        }
                    """)
                    self.folder2_edit.setToolTip("Folder locked by administrator")
                    
                    # Hide browse button for folder2
                    self.browse2_btn.setVisible(False)
                    
                    # Create/show refresh button for folder2
                    if not hasattr(self, 'refresh2_btn'):
                        self.refresh2_btn = QPushButton("🔄 Refresh")
                        self.refresh2_btn.setToolTip("Refresh file list")
                        self.refresh2_btn.clicked.connect(self._update_counts)
                        self.refresh2_btn.setStyleSheet("""
                            QPushButton {
                                background-color: #6c757d;
                                color: white;
                                font-weight: bold;
                                padding: 6px 12px;
                                border-radius: 4px;
                            }
                            QPushButton:hover {
                                background-color: #5a6268;
                            }
                        """)
                        # Need to add to folder2 layout (not stored, so find parent layout)
                        folder2_parent = self.folder2_edit.parent().layout()
                        if folder2_parent:
                            folder2_parent.addWidget(self.refresh2_btn)
                    else:
                        self.refresh2_btn.setVisible(True)
                else:
                    # Folder 2 path invalid, show warning but don't block
                    if not self.same_folder.isChecked():  # Only warn if in separate mode
                        QMessageBox.warning(
                            self,
                            "Admin Settings Warning",
                            f"Fixed folder path 2 does not exist:\\n{settings.fixed_folder_path_2}\\n\\n"
                            "Folder 2 will remain editable."
                        )
            
            # Setup auto-refresh timer if enabled
            if settings.auto_refresh_enabled:
                if not hasattr(self, 'auto_refresh_timer'):
                    self.auto_refresh_timer = QTimer(self)
                    self.auto_refresh_timer.timeout.connect(self._update_counts)
                self.auto_refresh_timer.start(settings.auto_refresh_interval * 1000)
            else:
                if hasattr(self, 'auto_refresh_timer'):
                    self.auto_refresh_timer.stop()
        else:
            # Normal mode - allow browsing
            self.folder1_edit.setReadOnly(False)
            self.folder1_edit.setStyleSheet("")
            self.folder1_edit.setToolTip("Folder for Server 1 (or shared folder when odd/even split is enabled)")
            self.browse1_btn.setVisible(True)
            
            self.folder2_edit.setReadOnly(False)
            self.folder2_edit.setStyleSheet("")
            self.folder2_edit.setToolTip("Folder for Server 2 (disabled when odd/even split is enabled)")
            self.browse2_btn.setVisible(True)
            
            if hasattr(self, 'refresh1_btn'):
                self.refresh1_btn.setVisible(False)
            if hasattr(self, 'refresh2_btn'):
                self.refresh2_btn.setVisible(False)
            if hasattr(self, 'auto_refresh_timer'):
                self.auto_refresh_timer.stop()
    
    def _apply_operator_controls(self, settings):
        """Apply operator control visibility settings"""
        
        # Copies/Collate controls
        self.copies_spin.setVisible(settings.enable_copies_collate)
        self.collate_type1.setVisible(settings.enable_copies_collate)
        self.collate_type2.setVisible(settings.enable_copies_collate)
        
        # If disabled, set default values
        if not settings.enable_copies_collate:
            self.copies_spin.setValue(1)
            self.collate_type1.setChecked(True)
        
        # Specify Range control
        self.range_spec.setVisible(settings.enable_specify_range)
        if not settings.enable_specify_range:
            self.range_all.setChecked(True)
        
        # Reverse Order control
        self.reverse_order.setVisible(settings.enable_reverse_order)
        if not settings.enable_reverse_order:
            self.reverse_order.setChecked(False)
        
        # Note: Continuous Mode doesn't exist in Dual Server, so we skip it
    
    def _deduplicate_color_planes(self, file_list):
        """Remove duplicate color plane files, keeping only _0 or first found"""
        from pathlib import Path
        
        base_name_map = {}
        
        for file_path in file_list:
            # Get base name without color plane suffix
            path = Path(file_path)
            stem = path.stem
            extension = path.suffix
            
            # Check if filename ends with _0, _1, _2, or _3
            if len(stem) >= 2 and stem[-2] == '_' and stem[-1].isdigit():
                base_stem = stem[:-2]
                base_name = str(path.parent / f"{base_stem}{extension}").lower()
            else:
                base_name = str(file_path).lower()
            
            if base_name not in base_name_map:
                base_name_map[base_name] = file_path
            else:
                # Prefer _0 plane
                if '_0.' in Path(file_path).name.lower():
                    base_name_map[base_name] = file_path
        
        return list(base_name_map.values())
    
    def _expand_color_plane_files(self, file_path: Path) -> list:
        """
        Find all color plane variants (_0, _1, _2, _3) for a given file.
        Returns list of existing color plane files.
        
        Example:
            image_0001_0.bmp -> [image_0001_0.bmp, image_0001_1.bmp, image_0001_2.bmp, image_0001_3.bmp]
        """
        # Get base name without color plane suffix
        stem = file_path.stem  # filename without extension
        extension = file_path.suffix
        parent = file_path.parent
        
        # Check if filename ends with _0, _1, _2, or _3
        if len(stem) >= 2 and stem[-2] == '_' and stem[-1].isdigit():
            # Remove the _X suffix to get base name
            base_stem = stem[:-2]
        else:
            # No color plane suffix, use as-is
            base_stem = stem
        
        # Find all color plane variants
        color_plane_files = []
        for plane in [0, 1, 2, 3]:
            variant_path = parent / f"{base_stem}_{plane}{extension}"
            if variant_path.exists():
                color_plane_files.append(variant_path)
        
        # If no color plane variants found, return original file if it exists
        if not color_plane_files and file_path.exists():
            color_plane_files.append(file_path)
        
        return color_plane_files
    
    def _execute_post_print_action(self, files_list: list, use_dest_2: bool = False):
        """Execute configured post-print action on specific printed files"""
        from ...shared.admin_config import AdminConfigManager
        from pathlib import Path
        import shutil
        from PySide6.QtWidgets import QMessageBox
        
        try:
            config_manager = AdminConfigManager()
            settings = config_manager.load_settings()
            
            if settings.post_print_action == "no_action":
                # Do nothing
                return
            
            # Convert file paths to Path objects and expand to include all color planes
            expanded_file_list = []
            for f in files_list:
                file_path = Path(f)
                if file_path.exists():
                    # Find all color plane variants for this file
                    color_plane_files = self._expand_color_plane_files(file_path)
                    expanded_file_list.extend(color_plane_files)
            
            # Remove duplicates while preserving order
            seen = set()
            file_list = []
            for file_path in expanded_file_list:
                if file_path not in seen:
                    seen.add(file_path)
                    file_list.append(file_path)
            
            if not file_list:
                return  # No files to process
            
            if settings.post_print_action == "delete":
                # Delete files permanently
                import os
                deleted_count = 0
                failed_files = []
                
                for file_path in file_list:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                    except Exception as e:
                        failed_files.append((file_path.name, str(e)))
                
                # Show result message
                if failed_files:
                    error_msg = f"Deleted {deleted_count} files.\\n\\nFailed to delete:\\n"
                    for file, error in failed_files[:5]:  # Show first 5 errors
                        error_msg += f"- {file}: {error}\\n"
                    if len(failed_files) > 5:
                        error_msg += f"... and {len(failed_files) - 5} more"
                    QMessageBox.warning(self, "Post-Print Delete", error_msg)
                else:
                    self.log1.append(f"✓ Post-print: Deleted {deleted_count} files")
            
            elif settings.post_print_action == "move":
                # Determine destination
                target_dest = settings.move_destination
                if use_dest_2 and settings.move_destination_2:
                    target_dest = settings.move_destination_2
                
                # Move files to destination
                if not target_dest:
                    QMessageBox.warning(
                        self,
                        "Post-Print Error",
                        "Move destination not configured. Files were not moved."
                    )
                    return
                
                dest_path = Path(target_dest)
                if not dest_path.exists():
                    try:
                        dest_path.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        QMessageBox.critical(
                            self,
                            "Post-Print Error",
                            f"Failed to create destination folder:\\n{str(e)}"
                        )
                        return
                
                moved_count = 0
                failed_files = []
                
                for file_path in file_list:
                    try:
                        source = Path(file_path)
                        destination = dest_path / source.name
                        
                        # Handle duplicate filenames
                        if destination.exists():
                            base = destination.stem
                            ext = destination.suffix
                            counter = 1
                            while destination.exists():
                                destination = dest_path / f"{base}_{counter}{ext}"
                                counter += 1
                        
                        shutil.move(str(source), str(destination))
                        moved_count += 1
                    except Exception as e:
                        failed_files.append((file_path.name, str(e)))
                
                # Show result message
                if failed_files:
                    error_msg = f"Moved {moved_count} files to {target_dest}.\\n\\nFailed to move:\\n"
                    for file, error in failed_files[:5]:
                        error_msg += f"- {file}: {error}\\n"
                    if len(failed_files) > 5:
                        error_msg += f"... and {len(failed_files) - 5} more"
                    QMessageBox.warning(self, "Post-Print Move", error_msg)
                else:
                    self.log1.append(f"✓ Post-print: Moved {moved_count} files to {target_dest}")
        
        except Exception as e:
            QMessageBox.critical(
                self,
                "Post-Print Error",
                f"Failed to execute post-print action:\\n{str(e)}"
            )


    def _log_print_job(self):
        """Log print job to production logs"""
        try:
            from ...shared.production_logger import ProductionLogger
            from pathlib import Path
            
            logger = ProductionLogger()
            
            # Interleave Server1 and Server2 entries for better readability
            max_len = max(len(self._print_job_files1), len(self._print_job_files2))
            
            for i in range(max_len):
                # Log Server1 file if available
                if i < len(self._print_job_files1):
                    file_path = Path(self._print_job_files1[i])
                    filename = file_path.name
                    
                    logger.log_print_job(
                        server="Server1",
                        filename=filename,
                        pages=1,  # Assume 1 page per file for now
                        copies=self._print_job_copies,
                        mode="Dual"
                    )
                
                # Log Server2 file if available
                if i < len(self._print_job_files2):
                    file_path = Path(self._print_job_files2[i])
                    filename = file_path.name
                    
                    logger.log_print_job(
                        server="Server2",
                        filename=filename,
                        pages=1,  # Assume 1 page per file for now
                        copies=self._print_job_copies,
                        mode="Dual"
                    )
            
            # Clear tracked files after logging
            self._print_job_files1 = []
            self._print_job_files2 = []
            
        except Exception as e:
            logging.error(f"Error logging print job: {e}")
            # Don't show error to user - logging failure shouldn't interrupt workflow
    
    def _check_reprint_detection(self, files_list):
        """Check for duplicate files before printing. Returns True to proceed, False to cancel."""
        try:
            from pages.multi_server_print.shared.admin_config import AdminConfigManager
            from pages.multi_server_print.shared.print_history_db import PrintHistoryDB
            from pages.multi_server_print.shared.reprint_warning_dialog import ReprintWarningDialog
            from PySide6.QtWidgets import QMessageBox
            
            # Load admin settings
            config_mgr = AdminConfigManager()
            settings = config_mgr.load_settings()
            
            # If detection disabled, proceed
            if not settings.enable_reprint_detection:
                return True
            
            # Check each file for duplicates
            db = PrintHistoryDB()
            duplicates = []
            
            for file_path_str in files_list:
                dup_info = db.check_duplicate(file_path_str)
                if dup_info:
                    duplicates.append(dup_info)
            
            # No duplicates found - proceed
            if not duplicates:
                return True
            
            # Handle based on mode
            if settings.reprint_mode == "allowed":
                # Allowed mode - proceed without warning
                return True
                
            elif settings.reprint_mode == "warning":
                # Warning mode - show dialog, let user decide
                from PySide6.QtWidgets import QDialog
                dialog = ReprintWarningDialog(duplicates, self)
                result = dialog.exec()
                return result == QDialog.DialogCode.Accepted
                
            elif settings.reprint_mode == "not_allowed":
                # Not allowed mode - block with error
                QMessageBox.critical(
                    self,
                    "Reprint Blocked",
                    f"Cannot print: {len(duplicates)} file(s) have already been printed.\n\n"
                    "Reprint detection is set to 'Not Allowed' mode.\n"
                    "Contact administrator to change settings or clear history."
                )
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"Error checking reprint detection: {e}")
            # On error, allow printing to continue
            return True
    
    def _record_to_history(self, files_list, server_name):
        """Record printed files to history database using optimized batch insert."""
        try:
            from pages.multi_server_print.shared.admin_config import AdminConfigManager
            from pages.multi_server_print.shared.print_history_db import PrintHistoryDB
            
            # Load admin settings
            config_mgr = AdminConfigManager()
            settings = config_mgr.load_settings()
            
            # If detection disabled, don't record
            if not settings.enable_reprint_detection:
                return
            
            # Batch insert all files in one transaction (OPTIMIZED)
            db = PrintHistoryDB()
            db.add_print_records_batch(
                file_paths=files_list,
                server_name=server_name,
                mode="Dual",
                retention_days=settings.history_retention_days
            )
                
        except Exception as e:
            logging.error(f"Error recording to history: {e}")
            # Don't show error to user - history recording failure shouldn't interrupt workflow

