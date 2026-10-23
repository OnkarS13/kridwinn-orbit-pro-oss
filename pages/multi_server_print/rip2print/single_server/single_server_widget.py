import os
import logging
from pathlib import Path
from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QSpinBox, QComboBox, QRadioButton, QButtonGroup, QCheckBox,
    QProgressBar, QTextEdit, QFileDialog, QMessageBox, QScrollArea
)
from .single_server_worker import SingleServerWorker
from .single_server_worker_real import SingleServerPrintWorkerReal
from ..shared.live_status_widget import LiveStatusWidget
from ...shared import __init__ as _shared  # noqa: F401 (package import for relative base)


class SingleServerWidget(QWidget):
    """Single Server job submission UI for RIP2PRINT."""

    def __init__(self, server_manager=None, parent=None):
        super().__init__(parent)
        self.server_manager = server_manager

        main = QVBoxLayout(self)

        # Wrap content in a scroll area to avoid squeezing on smaller heights
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)

        # Server selection
        server_group = QGroupBox("Server")
        sg_layout = QHBoxLayout()
        sg_layout.addWidget(QLabel("Select Server:"))
        self.server_combo = QComboBox()
        self.server_combo.setToolTip("Choose the target GIS print server")
        sg_layout.addWidget(self.server_combo)
        
        # Batch size display
        self.batch_size_label = QLabel("Queue Batch: 10")
        self.batch_size_label.setStyleSheet("color: #6c757d; font-size: 9pt;")
        self.batch_size_label.setToolTip("Number of files sent to printer queue at once (configured in Admin Panel)")
        sg_layout.addSpacing(20)
        sg_layout.addWidget(self.batch_size_label)
        
        server_group.setLayout(sg_layout)
        content_layout.addWidget(server_group)

        # RIP Folder
        folder_group = QGroupBox("RIP Folder")
        fg_layout = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Select RIP folder containing images...")
        self.folder_edit.setToolTip("Folder containing RIP images to print (no subfolders)")
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse_folder)
        fg_layout.addWidget(self.folder_edit)
        fg_layout.addWidget(self.browse_btn)
        self.folder_layout = fg_layout  # Store layout for adding refresh button later
        folder_group.setLayout(fg_layout)
        content_layout.addWidget(folder_group)

        # File count only (pattern removed - auto-detects all .bmp/.tif/.tiff)
        pattern_group = QGroupBox("Files")
        pg_layout = QHBoxLayout()
        self.file_count_label = QLabel("Files detected: 0")
        self.file_count_label.setToolTip("Auto-detects all .bmp, .tif, and .tiff files (case-insensitive)")
        pg_layout.addWidget(self.file_count_label)
        pg_layout.addStretch()
        pattern_group.setLayout(pg_layout)
        content_layout.addWidget(pattern_group)

        # File Groups Summary Panel
        self.groups_summary_group = QGroupBox("File Groups")
        self.groups_summary_group.setVisible(False)  # Hidden initially

        gsg_layout = QVBoxLayout()

        # Summary header label
        self.groups_summary_label = QLabel("No groups detected")
        self.groups_summary_label.setStyleSheet("color: #666; font-style: italic;")
        gsg_layout.addWidget(self.groups_summary_label)

        # Groups list widget (scrollable if many groups)
        self.groups_list_widget = QTextEdit()
        self.groups_list_widget.setReadOnly(True)
        self.groups_list_widget.setMaximumHeight(100)  # Compact, scrollable
        self.groups_list_widget.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 5px;
                font-family: monospace;
                font-size: 9pt;
            }
        """)
        gsg_layout.addWidget(self.groups_list_widget)

        self.groups_summary_group.setLayout(gsg_layout)
        content_layout.addWidget(self.groups_summary_group)

        # Copies and collation
        copies_group = QGroupBox("Copies & Collation")
        cg_layout = QHBoxLayout()
        cg_layout.addWidget(QLabel("Copies:"))
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 100)
        self.copies_spin.setValue(1)
        self.copies_spin.setToolTip("Number of copies per page in the print sequence")
        cg_layout.addWidget(self.copies_spin)
        cg_layout.addStretch()
        self.collate_type1 = QRadioButton("Collate Type 1 (range × copies)")
        self.collate_type2 = QRadioButton("Collate Type 2 (copies per page × range)")
        self.collate_type1.setToolTip("Print full range, then repeat for each copy")
        self.collate_type2.setToolTip("Print each page N times before moving to next")
        self.collate_type1.setChecked(True)
        self.collation_group = QButtonGroup(self)
        self.collation_group.addButton(self.collate_type1)
        self.collation_group.addButton(self.collate_type2)
        cg_layout.addWidget(self.collate_type1)
        cg_layout.addWidget(self.collate_type2)
        copies_group.setLayout(cg_layout)
        content_layout.addWidget(copies_group)

        # Page range
        range_group = QGroupBox("Page Range")
        rg_layout = QHBoxLayout()
        self.range_all = QRadioButton("All pages")
        self.range_spec = QRadioButton("Specify range")
        self.range_all.setToolTip("Print all detected files")
        self.range_spec.setToolTip("Print only the specified page range (by file order)")
        self.range_all.setChecked(True)
        rg_layout.addWidget(self.range_all)
        rg_layout.addWidget(self.range_spec)
        rg_layout.addStretch()
        rg_layout.addWidget(QLabel("From"))
        self.range_from = QSpinBox()
        self.range_from.setRange(1, 1_000_000)
        self.range_from.setValue(1)
        self.range_from.setToolTip("Range start index (1-based)")
        rg_layout.addWidget(self.range_from)
        rg_layout.addWidget(QLabel("to"))
        self.range_to = QSpinBox()
        self.range_to.setRange(1, 1_000_000)
        self.range_to.setValue(1)  # User must set the end range explicitly
        self.range_to.setToolTip("Range end index (1-based) - Set this to the last page you want to print")
        self.range_to.setSpecialValueText("")  # Show empty when at minimum
        rg_layout.addWidget(self.range_to)
        range_group.setLayout(rg_layout)
        content_layout.addWidget(range_group)

        # Order vs Continuous (mutually exclusive)
        mode_group = QGroupBox("Order / Mode")
        mg_layout = QHBoxLayout()
        self.reverse_order = QCheckBox("Reverse Order")
        self.continuous_mode = QCheckBox("Continuous Mode")
        self.reverse_order.setToolTip("Print in reverse sequence order")
        self.continuous_mode.setToolTip("Monitor folder and print new files as they arrive")
        mg_layout.addWidget(self.reverse_order)
        mg_layout.addWidget(self.continuous_mode)
        mg_layout.addStretch()
        mode_group.setLayout(mg_layout)
        content_layout.addWidget(mode_group)

        # Progress & log
        progress_group = QGroupBox("Progress")
        pr_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar { color: black; }")
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setPlaceholderText("Status log will appear here...")
        self.status_log.setMinimumHeight(240)
        self.status_log.setStyleSheet("font-size: 11pt;")
        pr_layout.addWidget(self.progress_bar)
        pr_layout.addWidget(self.status_log)
        pr_layout.setStretch(0, 0)
        pr_layout.setStretch(1, 1)
        progress_group.setLayout(pr_layout)
        content_layout.addWidget(progress_group)

        # Live status widget
        self.live_status = LiveStatusWidget()
        self.live_status.setVisible(False)
        content_layout.addWidget(self.live_status)

        # Actions
        actions_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Printing")
        self.stop_btn = QPushButton("Stop/Pause")
        self.resume_btn = QPushButton("Resume")
        self.stop_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.resume_btn.setVisible(False)
        self.start_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.stop_btn.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
        self.resume_btn.setStyleSheet("background-color: #0d6efd; color: white; font-weight: bold;")
        self.start_btn.setToolTip("Begin printing with current configuration")
        self.stop_btn.setToolTip("Stop or pause the current print job (can be resumed)")
        self.resume_btn.setToolTip("Resume printing from where it was stopped")
        actions_layout.addWidget(self.start_btn)
        actions_layout.addWidget(self.stop_btn)
        actions_layout.addWidget(self.resume_btn)
        content_layout.addLayout(actions_layout)

        # Finalize scroll
        scroll.setWidget(content)
        main.addWidget(scroll, 1)

        # Signals for dynamic behavior
        self.folder_edit.textChanged.connect(self._update_file_count)
        self.range_spec.toggled.connect(self._toggle_range_inputs)
        self.range_all.toggled.connect(self._toggle_range_inputs)
        self.reverse_order.toggled.connect(self._enforce_mode_mutex)
        self.continuous_mode.toggled.connect(self._enforce_mode_mutex)

        self._toggle_range_inputs()
        self._update_file_count()

        # Wire actions
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)
        self.resume_btn.clicked.connect(self._resume)
        
        # Ensure start button is explicitly enabled
        self.start_btn.setEnabled(True)

        # Populate servers
        self._populate_servers()
        # Live update when servers are added/updated/removed
        if self.server_manager is not None:
            try:
                self.server_manager.server_added.connect(lambda _sid: self._populate_servers())
                self.server_manager.server_updated.connect(lambda _sid: self._populate_servers())
                self.server_manager.server_removed.connect(lambda _sid: self._populate_servers())
            except Exception:
                pass
        # Re-populate whenever the widget becomes visible (covers server changes)
        try:
            self.window().windowTitleChanged.connect(lambda _t=None: self._populate_servers())
        except Exception:
            pass
        
        # Runtime state variables
        self._worker = None
        self._thread = None
        self._resume_state = None  # Store resume state from stopped worker
        self._threads_finishing = False  # Flag to track if threads are finishing
        self._print_job_files = []  # Track files for logging
        self._print_job_copies = 1  # Track copies for logging
        self._using_per_group_mode = False  # Track if per-group mode is active (for logging)
        self._skip_reprint_warning_this_session = False  # Track "don't show again" for session
        self._batch_size = 10  # Default batch size (overridden by admin settings)
        self._resume_repeat_pages = 1  # Default pages to re-print on resume (overridden by admin settings)
        
        # Load and apply admin settings
        self._load_and_apply_admin_settings()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select RIP Folder", self.folder_edit.text() or os.getcwd())
        if folder:
            self.folder_edit.setText(folder)

    def _update_file_count(self):
        folder = self.folder_edit.text().strip()
        count = 0
        try:
            if folder and Path(folder).is_dir():
                # Count all .bmp, .tif, .tiff files (case-insensitive, deduplicated)
                patterns = ['*.bmp', '*.BMP', '*.tif', '*.TIF', '*.tiff', '*.TIFF']
                files_set = set()
                for pat in patterns:
                    for f in Path(folder).glob(pat):
                        files_set.add(str(f))  # Keep original case for deduplication

                # Convert to list and deduplicate color planes to get actual page count
                files_list = list(files_set)
                files_list = self._deduplicate_color_planes(files_list)
                count = len(files_list)  # Now counts pages, not individual files
        except Exception:
            count = 0
        self.file_count_label.setText(f"Files detected: {count}")
        
        # Update range spinboxes maximum to match actual file count
        if count > 0:
            self.range_from.setMaximum(count)
            self.range_to.setMaximum(count)
            # Update tooltips to show the valid range
            self.range_from.setToolTip(f"Range start index (1-based) - Max: {count}")
            self.range_to.setToolTip(f"Range end index (1-based) - Max: {count} - Set this to the last page you want to print")
            # Auto-populate "To" field with total file count (F.b fix)
            # Always set to file count to auto-populate the range
            self.range_to.setValue(count)
            # If "From" value exceeds count, adjust it
            if self.range_from.value() > count:
                self.range_from.setValue(1)
        else:
            # Reset to default if no files
            self.range_from.setMaximum(1_000_000)
            self.range_to.setMaximum(1_000_000)
            self.range_from.setToolTip("Range start index (1-based)")
            self.range_to.setToolTip("Range end index (1-based) - Set this to the last page you want to print")

        # Trigger group detection to update File Groups panel
        self._detect_and_display_groups()

    def _detect_and_display_groups(self):
        """Detect file groups and update summary panel"""
        try:
            # Get current folder
            folder_path = self.folder_edit.text().strip()
            if not folder_path or not Path(folder_path).exists():
                self.groups_summary_group.setVisible(False)
                return

            # Load files from folder (same logic as _update_file_count)
            folder = Path(folder_path)
            patterns = ['*.bmp', '*.BMP', '*.tif', '*.TIF', '*.tiff', '*.TIFF']
            files_set = set()
            for pat in patterns:
                for f in folder.glob(pat):
                    files_set.add(str(f))

            files_list = list(files_set)
            if not files_list:
                self.groups_summary_group.setVisible(False)
                return

            # Check if grouping is enabled
            from ...shared.admin_config import AdminConfigManager
            config_manager = AdminConfigManager()
            settings = config_manager.load_settings()

            if not settings.enable_file_grouping:
                self.groups_summary_group.setVisible(False)
                return

            # Deduplicate color planes (same as _update_file_count logic)
            files_list = self._deduplicate_color_planes(files_list)

            # Convert to Path objects for grouping
            files = [Path(f) for f in files_list]

            # Group files
            from ..shared.file_grouping import group_files
            groups = group_files(files)

            if not groups:
                self.groups_summary_group.setVisible(False)
                return

            # Update UI
            self._update_groups_summary(groups)

        except Exception as e:
            logging.error(f"Error detecting groups: {e}")
            self.groups_summary_group.setVisible(False)

    def _update_groups_summary(self, groups):
        """Update the groups summary panel with detected groups"""
        if not groups:
            self.groups_summary_group.setVisible(False)
            return

        # Calculate totals
        total_groups = len(groups)
        total_files = sum(len(files) for files in groups.values())

        # Update summary header
        self.groups_summary_label.setText(
            f"📊 {total_groups} group{'' if total_groups == 1 else 's'}, "
            f"{total_files} total file{'' if total_files == 1 else 's'}"
        )
        self.groups_summary_label.setStyleSheet("color: #28a745; font-weight: bold;")

        # Build groups list text
        groups_text = ""
        for group_name, files in sorted(groups.items()):
            page_count = len(files)
            groups_text += f"• {group_name:<30} [{page_count:>3} pages]\n"

        self.groups_list_widget.setPlainText(groups_text.strip())

        # Show the panel
        self.groups_summary_group.setVisible(True)

    def _toggle_range_inputs(self):
        enabled = self.range_spec.isChecked()
        self.range_from.setEnabled(enabled)
        self.range_to.setEnabled(enabled)

    def _enforce_mode_mutex(self):
        # Ensure only one checkbox is active at a time (mutually exclusive)
        # Allow both to be unchecked (normal mode)
        sender = self.sender()
        if sender is self.reverse_order and self.reverse_order.isChecked():
            # If reverse order is checked, uncheck continuous mode
            self.continuous_mode.setChecked(False)
        elif sender is self.continuous_mode and self.continuous_mode.isChecked():
            # If continuous mode is checked, uncheck reverse order
            self.reverse_order.setChecked(False)

    def _start(self):
        logging.debug("_start() method called - button click received!")
        folder = self.folder_edit.text().strip()
        pattern = "*.bmp"  # Ignored by worker, kept for compatibility
        copies = self.copies_spin.value()
        collate_type = 1 if self.collate_type1.isChecked() else 2
        range_mode_all = self.range_all.isChecked()
        r_from = self.range_from.value()
        r_to = self.range_to.value()
        reverse = self.reverse_order.isChecked()
        cont = self.continuous_mode.isChecked()

        # Validate inputs
        if copies < 1:
            self.status_log.append("Copies must be at least 1.")
            return
        if not range_mode_all:
            if r_from == 1 and r_to == 1:
                self.status_log.append("⚠️ Warning: Range is set to print only page 1. If you want to print more pages, please adjust the 'to' value.")
                # Allow it to continue - user might actually want to print just page 1
            low = max(1, min(r_from, r_to))
            high = max(r_from, r_to)
            if low > high:
                self.status_log.append("Invalid page range: From must be <= To.")
                return
        if reverse and cont:
            self.status_log.append("Choose either Reverse Order or Continuous Mode, not both.")
            return

        # Resolve selected server
        sid = self.server_combo.currentData()
        server = self._get_server_by_id(sid)
        # Basic validations
        if not server:
            self.status_log.append("Select a server before starting.")
            return
        if not folder or not Path(folder).is_dir():
            self.status_log.append("Select a valid RIP folder.")
            return
        
        # Check for any RIP files (all extensions, deduplicated)
        patterns = ['*.bmp', '*.BMP', '*.tif', '*.TIF', '*.tiff', '*.TIFF']
        files_set = set()
        for pat in patterns:
            for f in Path(folder).glob(pat):
                # Store original path (not lowercase) for proper file operations
                files_set.add(str(f.absolute()))
        
        # Deduplicate by lowercase comparison but keep original paths
        unique_files = {}
        for f in files_set:
            key = f.lower()
            if key not in unique_files:
                unique_files[key] = f
        files_set = set(unique_files.values())
        
        if not files_set:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "No Files Found",
                "No RIP files found in the selected folder.\n\nPlease select a folder containing .bmp, .tif, or .tiff files."
            )
            return
        
        # Convert to list and apply natural sorting for proper alphanumeric order
        # This ensures files are sorted as: 1, 2, 3... 10, 11, 12 (not 1, 10, 11, 2, 3...)
        import re
        def natural_sort_key(path):
            """Extract filename and split into text/number parts for natural sorting"""
            filename = Path(path).name
            return [int(text) if text.isdigit() else text.lower() 
                    for text in re.split(r'(\d+)', filename)]
        
        files_list = sorted(list(files_set), key=natural_sort_key)
        
        # Deduplicate color plane files before grouping
        files_list = self._deduplicate_color_planes(files_list)
        
        # Check for multi-group scenario (Phase 8: File Grouping)
        # If admin enabled file grouping and multiple PDF groups detected, show selector
        from ...shared.admin_config import AdminConfigManager
        config_mgr = AdminConfigManager()
        settings = config_mgr.load_settings()

        # Flag to track if we're using per-group settings
        has_group_settings = False
        group_settings = None
        print_order = None
        groups = {}
        selected_group_names = []
        total_pages = 0

        if settings.enable_file_grouping:
            from ..shared.file_grouping import group_files
            from ..shared.file_group_selector import FileGroupSelector

            groups = group_files(files_list)

            # DEBUG: Log detected groups
            self.status_log.append("=" * 60)
            self.status_log.append(f"📋 DEBUG: File Grouping Analysis")
            self.status_log.append(f"Total files loaded: {len(files_list)}")
            self.status_log.append(f"Groups detected: {len(groups)}")
            for group_name, group_files in groups.items():
                self.status_log.append(f"  • Group '{group_name}': {len(group_files)} files")
            self.status_log.append("=" * 60)

            # If groups detected, show selector (even for single group)
            if len(groups) >= 1:
                self.status_log.append(f"Detected {len(groups)} file group(s) from PDF(s)")

                # Build global settings from UI controls to pass as defaults
                global_settings = {
                    'range_mode': 'all' if range_mode_all else 'range',
                    'range_from': r_from,
                    'range_to': r_to,
                    'copies': copies,
                    'collate_type': collate_type,
                    'reverse': reverse,
                }

                dialog = FileGroupSelector(groups, global_settings, self)
                if dialog.exec() != FileGroupSelector.Accepted:
                    self.status_log.append("Print job cancelled by user")
                    return  # User cancelled

                # Get per-group settings and print order
                group_settings = dialog.get_group_settings()
                print_order = dialog.get_print_order()
                has_group_settings = True

                # Also get flat files list for backward compatibility and logging
                files_list = dialog.get_selected_files()
                total_pages = dialog.get_total_pages()
                selected_group_names = dialog.get_selected_groups()
                
                # DEBUG: Log selection and order
                self.status_log.append("=" * 60)
                self.status_log.append(f"✅ DEBUG: User Selection")
                self.status_log.append(f"Selected groups: {len(selected_group_names)}")
                for idx, group_name in enumerate(selected_group_names, 1):
                    group_file_count = len(groups[group_name])
                    self.status_log.append(f"  {idx}. '{group_name}' ({group_file_count} files)")
                self.status_log.append(f"Total files to print: {total_pages}")
                self.status_log.append("=" * 60)
                
                # DEBUG: Log exact file order (first 10 files)
                self.status_log.append("📄 DEBUG: Print Order (first 10 files):")
                for idx, file_path in enumerate(files_list[:10], 1):
                    filename = Path(file_path).name
                    self.status_log.append(f"  {idx}. {filename}")
                if len(files_list) > 10:
                    self.status_log.append(f"  ... and {len(files_list) - 10} more files")
                self.status_log.append("=" * 60)
                
                self.status_log.append(f"Selected {len(selected_group_names)} group(s), {total_pages} page(s)")
        
        server_ip = server.ip
        server_port = server.port

        # Apply page range filter to get the actual files that will be printed
        # This ensures database only records files that are actually printed
        # IMPORTANT: Skip this if using per-group settings (worker handles filtering)
        files_to_print = files_list
        if not has_group_settings and not range_mode_all:
            # Apply the same range logic as the worker (only for non-group mode)
            low = max(1, min(r_from, r_to))
            high = max(r_from, r_to)
            files_to_print = [f for idx, f in enumerate(files_list, start=1) if low <= idx <= high]

        # Track files and copies for logging (use filtered list)
        # NOTE: For per-group mode, this is approximate (worker has actual filtered lists)
        # TODO: Implement proper per-group logging that tracks actual printed files
        self._print_job_files = files_to_print
        self._print_job_copies = copies
        self._using_per_group_mode = has_group_settings  # Track if per-group mode is active

        # Check for reprints if detection is enabled
        if not self._check_reprint_detection(self._print_job_files):
            return  # User cancelled or reprint blocked

        # SMART BATCH SIZE ANALYZER - Analyze folder and recommend optimal batch size
        from pages.rip_to_print.rip_to_print import GISPrintServerClient, RIPFolderPrinter, show_batch_size_recommendation_dialog

        try:
            # Create temporary client and printer for analysis (no connection needed)
            temp_client = GISPrintServerClient(host=server_ip, port=server_port)
            temp_printer = RIPFolderPrinter(
                client=temp_client,
                progress_callback=None,
                batch_size=self._batch_size
            )

            # Analyze folder and get recommendation
            analysis = temp_printer.analyze_folder_and_recommend_batch_size(
                folder_path=folder,
                pattern="*.bmp",
                recursive=False,
                current_batch_size=self._batch_size
            )

            # Show recommendation dialog and get user choice
            user_choice = show_batch_size_recommendation_dialog(self, analysis)

            if user_choice == 'cancel':
                self.status_log.append("❌ Print cancelled by user")
                return  # User cancelled
            elif user_choice == 'recommended':
                # User wants to use recommended batch size
                recommended_batch = analysis.get('recommended_batch_size', self._batch_size)
                self.status_log.append(f"✅ Using recommended batch size: {recommended_batch} pages")
                self.status_log.append(f"   (Previous: {self._batch_size} pages)")
                self._batch_size = recommended_batch  # Update for this print job
            else:  # 'continue'
                self.status_log.append(f"ℹ️ Continuing with current batch size: {self._batch_size} pages")

        except Exception as e:
            # If analyzer fails, just log and continue with current settings
            logger = logging.getLogger(__name__)
            logger.warning(f"Batch size analyzer failed: {e}")
            self.status_log.append(f"⚠️ Batch analyzer warning: {e}")
            self.status_log.append(f"ℹ️ Continuing with batch size: {self._batch_size}")

        # Clear any previous resume state when starting a new job
        self._resume_state = None
        self.resume_btn.setVisible(False)
        self.resume_btn.setEnabled(False)

        # Instantiate real worker and thread
        # Note: has_group_settings flag was set earlier if per-group mode is active
        self._worker = SingleServerPrintWorkerReal(
            server_ip, server_port, folder, pattern, copies, collate_type,
            range_mode_all, r_from, r_to, reverse, cont, resume_from_page=0,
            files_list=files_list,  # Pass full list - worker will apply range internally
            batch_size=self._batch_size,
            repeat_resume_pages=self._resume_repeat_pages,
            group_settings=group_settings if has_group_settings else None,
            print_order=print_order if has_group_settings else None,
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
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

        def _cleanup():
            try:
                # Just request quit without blocking - thread will clean up naturally
                self._thread.quit()
            except Exception:
                pass
        self._worker.finished.connect(_cleanup)

        self._set_printing_state(True)
        self.status_log.clear()
        
        # Re-display debug logs after clear (if file grouping was used)
        if settings.enable_file_grouping and len(groups) > 1:
            self.status_log.append("=" * 60)
            self.status_log.append(f"📋 File Grouping Analysis")
            self.status_log.append(f"Total files loaded: {len(files_list)}")
            self.status_log.append(f"Groups detected: {len(groups)}")
            for group_name, group_files in groups.items():
                self.status_log.append(f"  • Group '{group_name}': {len(group_files)} files")
            self.status_log.append("=" * 60)
            
            self.status_log.append(f"✅ User Selection")
            self.status_log.append(f"Selected groups: {len(selected_group_names)}")
            for idx, group_name in enumerate(selected_group_names, 1):
                group_file_count = len(groups[group_name])
                self.status_log.append(f"  {idx}. '{group_name}' ({group_file_count} files)")
            self.status_log.append(f"Total files to print: {total_pages}")
            self.status_log.append("=" * 60)
            
            self.status_log.append("📄 Print Order (first 10 files):")
            for idx, file_path in enumerate(files_list[:10], 1):
                filename = Path(file_path).name
                self.status_log.append(f"  {idx}. {filename}")
            if len(files_list) > 10:
                self.status_log.append(f"  ... and {len(files_list) - 10} more files")
            self.status_log.append("=" * 60)
        
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("QProgressBar { color: black; }")  # Reset progress bar style
        self.live_status.clear_error()  # Clear any previous error state
        self._thread.start()
        self.live_status.setVisible(True)

    def _stop(self):
        if self._worker:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                'Stop Printing',
                'Are you sure you want to stop the current print job?\n\nYou can resume it later from where it stopped.',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            
            # Update UI state immediately to give user feedback
            self._set_printing_state(False)
            self.status_log.append("Stopping print job...")
            
            try:
                self._worker.cancel()
                # Mark that threads are finishing
                self._threads_finishing = True
                
                # Save resume state from worker immediately
                if hasattr(self._worker, 'resume_state') and self._worker.resume_state:
                    self._resume_state = self._worker.resume_state
                    self.status_log.append(f"Print job stopped. Printed {self._resume_state.get('last_printed', 0)}/{self._resume_state.get('total', 0)} pages.")
                    # Show resume button but disable it until threads finish
                    self.resume_btn.setVisible(True)
                    self.resume_btn.setEnabled(False)
                    self.resume_btn.setText("Resume (waiting for thread to be cleared...)")
                else:
                    self.status_log.append("Cancelling print job...")
            except Exception as e:
                self.status_log.append(f"Stop error: {e}")
            
            # DON'T wait synchronously - let the thread finish naturally
            # The _on_finished callback will re-enable the resume button
            self.status_log.append("Print job will stop after current operation completes...")

    def _resume(self):
        """Resume printing from where it was stopped"""
        if not self._resume_state:
            self.status_log.append("No resume state available.")
            return
        
        # Safety check - should not happen if button is disabled correctly
        if self._threads_finishing:
            self.status_log.append("⚠️ Please wait for thread to finish...")
            return
        
        # At this point, _on_finished has already cleaned up the old thread
        # Just verify it's clean
        if self._thread is not None or self._worker is not None:
            self.status_log.append("⚠️ Warning: Old thread/worker still exists, cleaning up...")
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
                self.status_log.append(f"Cleanup warning: {e}")
        
        # Validate resume state
        folder_path = self._resume_state.get('folder_path')
        if not folder_path or not Path(folder_path).is_dir():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Resume Failed",
                f"Folder not found: {folder_path}\n\nCannot resume printing."
            )
            self._resume_state = None
            self.resume_btn.setVisible(False)
            return
        
        last_printed = self._resume_state.get('last_printed', 0)
        total = self._resume_state.get('total', 0)
        
        if last_printed >= total:
            self.status_log.append(f"Job already complete ({last_printed}/{total}). Nothing to resume.")
            self._resume_state = None
            self.resume_btn.setVisible(False)
            return
        
        # Extract all settings from resume state
        server_ip = self._resume_state.get('server_ip')
        server_port = self._resume_state.get('server_port')
        pattern = self._resume_state.get('pattern', '*.bmp')
        copies = self._resume_state.get('copies', 1)
        collate_type = self._resume_state.get('collate_type', 1)
        range_mode_all = self._resume_state.get('range_mode_all', True)
        r_from = self._resume_state.get('range_from', 1)
        r_to = self._resume_state.get('range_to', 1)
        reverse = self._resume_state.get('reverse_order', False)
        cont = self._resume_state.get('continuous_mode', False)
        batch_size = self._resume_state.get('batch_size', self._batch_size)
        files_list = self._resume_state.get('files_list', None)
        group_settings = self._resume_state.get('group_settings', None)
        print_order = self._resume_state.get('print_order', None)

        self.status_log.append(f"Resuming from page {last_printed + 1}/{total}...")

        # Create new worker starting from the next page
        self._worker = SingleServerPrintWorkerReal(
            server_ip, server_port, folder_path, pattern, copies, collate_type,
            range_mode_all, r_from, r_to, reverse, cont, resume_from_page=last_printed,
            files_list=files_list,
            batch_size=batch_size,
            repeat_resume_pages=self._resume_repeat_pages,
            group_settings=group_settings,
            print_order=print_order,
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
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
        
        def _cleanup():
            try:
                self._thread.quit()
            except Exception:
                pass
        self._worker.finished.connect(_cleanup)
        
        # Hide resume button during printing
        self.resume_btn.setVisible(False)
        self.resume_btn.setEnabled(False)
        
        self._set_printing_state(True)
        self._thread.start()
        self.live_status.setVisible(True)
    
    def _on_progress(self, current: int, total: int, message: str):
        # Calculate percentage correctly, capping at 100%
        if total > 0:
            pct = min(100, int((current / total) * 100))
        else:
            pct = 0
        self.progress_bar.setValue(pct)
        self.status_log.append(message)
        # With real worker, status_update will set live counters; keep progress bar/log here only

    def _on_finished(self, success: bool):
        self._set_printing_state(False)
        self.status_log.append("Done" if success else "Failed/Cancelled")
        
        # Mark threads as finished
        self._threads_finishing = False
        
        if success:
            # Clear resume state on successful completion
            self._resume_state = None
            self.resume_btn.setVisible(False)
            self.resume_btn.setEnabled(False)
            self.resume_btn.setText("Resume")
            
            # Record to history database FIRST (before clearing files list)
            self._record_to_history(self._print_job_files)
            
            # Execute post-print action on ONLY the printed files
            if self._print_job_files:
                self._execute_post_print_action(self._print_job_files)
            
            # Log print job (this clears the files list)
            self._log_print_job()
            
            
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Print Complete", "All files printed successfully.")
        else:
            # If failed/cancelled and we have resume state, enable the resume button
            if self._resume_state:
                self.resume_btn.setEnabled(True)
                self.resume_btn.setText("Resume")
                self.status_log.append("✓ Thread finished - Resume button is now ready")
        # keep live status visible to show final counts

    def _on_error(self, msg: str):
        # Large, visible error message in red/bold
        self.status_log.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ ERROR: {msg}</span>")
    
    def _on_error_detail(self, error_info: dict):
        """Handle detailed error with last known counts"""
        error_msg = error_info.get('error_msg', 'Unknown error')
        last_sent = error_info.get('sent', 0)
        last_printed = error_info.get('printed', 0)
        total = error_info.get('total', 0)

        # Show error in live status widget
        self.live_status.show_error(error_msg, last_sent, last_printed, total)

        # Turn progress bar red
        self.progress_bar.setStyleSheet("QProgressBar { color: black; } QProgressBar::chunk { background-color: #dc3545; }")

        # Add detailed error to log
        self.status_log.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")
        self.status_log.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ PRINT JOB FAILED</span>")
        self.status_log.append(f"<span style='color: #dc3545;'>Error: {error_msg}</span>")
        self.status_log.append(f"<span style='color: #6c757d;'>Last known status:</span>")
        self.status_log.append(f"<span style='color: #6c757d;'>  • Files Sent: {last_sent}/{total}</span>")
        self.status_log.append(f"<span style='color: #6c757d;'>  • Files Printed: {last_printed}/{total}</span>")
        self.status_log.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")

    def _on_server_error(self, error_details: dict):
        """Handle server error with auto-saved resume state and show popup"""
        error_type = error_details.get('error_type', 'UNKNOWN')
        error_msg = error_details.get('error_msg', 'Unknown server error')
        last_printed = error_details.get('last_printed', 0)
        total = error_details.get('total', 0)
        can_resume = error_details.get('can_resume', False)
        resume_from = error_details.get('resume_from', last_printed)

        # Update UI state
        self._set_printing_state(False)

        # Show error in live status widget
        self.live_status.show_error(f"{error_type}: {error_msg}", 0, last_printed, total)

        # Turn progress bar red
        self.progress_bar.setStyleSheet("QProgressBar { color: black; } QProgressBar::chunk { background-color: #dc3545; }")

        # Add detailed error to log
        self.status_log.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")
        self.status_log.append(f"<span style='color: #dc3545; font-weight: bold; font-size: 14pt;'>❌ SERVER ERROR DETECTED</span>")
        self.status_log.append(f"<span style='color: #dc3545;'>Error Type: {error_type}</span>")
        self.status_log.append(f"<span style='color: #dc3545;'>Error: {error_msg}</span>")
        self.status_log.append(f"<span style='color: #6c757d;'>Last printed page: {last_printed}/{total}</span>")
        if can_resume:
            self.status_log.append(f"<span style='color: #28a745; font-weight: bold;'>✅ Resume state saved automatically</span>")
            self.status_log.append(f"<span style='color: #6c757d;'>Will resume from page: {resume_from}</span>")
        self.status_log.append(f"<span style='color: #dc3545; font-weight: bold;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>")

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
        msg_box.setWindowTitle("Server Error Detected")

        if can_resume:
            msg_box.setText(f"<b>Print job stopped due to server error:</b><br><br>"
                           f"<span style='color: #dc3545;'>{error_type}</span><br>"
                           f"{error_msg}<br><br>"
                           f"<b>Progress:</b> {last_printed}/{total} pages printed<br><br>"
                           f"<span style='color: #28a745;'><b>✓ Resume state saved</b></span><br>"
                           f"Click <b>Resume</b> to continue from page {resume_from}")
            msg_box.setInformativeText("The print job has been automatically saved.\n"
                                      "You can resume printing by clicking the Resume button.")
        else:
            msg_box.setText(f"<b>Print job failed due to server error:</b><br><br>"
                           f"<span style='color: #dc3545;'>{error_type}</span><br>"
                           f"{error_msg}<br><br>"
                           f"<b>Progress:</b> {last_printed}/{total} pages printed")
            msg_box.setInformativeText("The print job cannot be resumed automatically.\n"
                                      "Please check the server status and try again.")

        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    def _on_status(self, status: dict):
        total = status.get('total', 0)
        sent = status.get('sent', 0)
        printed = status.get('printed', 0)
        speed = status.get('speed')
        self.live_status.update_status(sent, printed, total, speed)

    def _populate_servers(self):
        # Preserve current selection
        current_sid = self.server_combo.currentData()
        self.server_combo.clear()
        if not self.server_manager:
            return
        for sid, cfg in self.server_manager.get_all_servers().items():
            self.server_combo.addItem(f"{cfg.name} ({cfg.ip}:{cfg.port})", sid)
        # Restore selection if still present
        if current_sid is not None:
            index = self.server_combo.findData(current_sid)
            if index >= 0:
                self.server_combo.setCurrentIndex(index)

    def _get_server_by_id(self, sid):
        if not self.server_manager:
            return None
        return self.server_manager.get_server(sid)

    def _set_printing_state(self, printing: bool):
        # Disable controls during print
        self.start_btn.setEnabled(not printing)
        self.stop_btn.setEnabled(printing)
        self.server_combo.setEnabled(not printing)
        self.folder_edit.setEnabled(not printing)
        self.copies_spin.setEnabled(not printing)
        self.collate_type1.setEnabled(not printing)
        self.collate_type2.setEnabled(not printing)
        self.range_all.setEnabled(not printing)
        self.range_spec.setEnabled(not printing)
        self.range_from.setEnabled(not printing and self.range_spec.isChecked())
        self.range_to.setEnabled(not printing and self.range_spec.isChecked())
        self.reverse_order.setEnabled(not printing)
        self.continuous_mode.setEnabled(not printing)
    
    def _open_admin_panel(self):
        """Open admin panel with password authentication"""
        from ...shared.admin_auth import AdminAuthManager
        from ...shared.admin_password_setup_dialog import AdminPasswordSetupDialog
        from ...shared.admin_password_entry_dialog import AdminPasswordEntryDialog
        from ...shared.admin_settings_dialog import AdminSettingsDialog
        from PySide6.QtWidgets import QDialog
        
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
        from PySide6.QtWidgets import QDialog
        
        settings_dialog = AdminSettingsDialog(self)
        if settings_dialog.exec() == QDialog.Accepted:
            # Reload and apply settings after save
            self._load_and_apply_admin_settings()
    
    def _load_and_apply_admin_settings(self):
        """Load admin settings and apply to UI"""
        try:
            from ...shared.admin_config import AdminConfigManager
            
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
        
        if settings.fix_browse_folder and settings.fixed_folder_path:
            # Validate folder exists
            folder_path = Path(settings.fixed_folder_path)
            if not folder_path.exists() or not folder_path.is_dir():
                QMessageBox.warning(
                    self,
                    "Admin Settings Error",
                    f"Fixed folder does not exist:\n{settings.fixed_folder_path}\n\n"
                    "Contact administrator to update the folder path."
                )
                return
            
            # Set the fixed folder
            self.folder_edit.setText(settings.fixed_folder_path)
            self.folder_edit.setReadOnly(True)
            self.folder_edit.setStyleSheet("""
                QLineEdit {
                    background-color: #f8f9fa;
                    border: 1px dashed #6c757d;
                    color: #495057;
                }
            """)
            self.folder_edit.setToolTip("Folder locked by administrator")
            
            # Hide browse button
            self.browse_btn.setVisible(False)
            
            # Create/show refresh button
            if not hasattr(self, 'refresh_btn'):
                self.refresh_btn = QPushButton("🔄 Refresh")
                self.refresh_btn.setToolTip("Refresh file list")
                self.refresh_btn.clicked.connect(self._update_file_count)
                self.refresh_btn.setStyleSheet("""
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
                self.folder_layout.addWidget(self.refresh_btn)
            else:
                self.refresh_btn.setVisible(True)
            
            # Setup auto-refresh timer if enabled
            if settings.auto_refresh_enabled:
                if not hasattr(self, 'auto_refresh_timer'):
                    self.auto_refresh_timer = QTimer(self)
                    self.auto_refresh_timer.timeout.connect(self._update_file_count)
                self.auto_refresh_timer.start(settings.auto_refresh_interval * 1000)
            else:
                if hasattr(self, 'auto_refresh_timer'):
                    self.auto_refresh_timer.stop()
        else:
            # Normal mode - allow browsing
            self.folder_edit.setReadOnly(False)
            self.folder_edit.setStyleSheet("")
            self.folder_edit.setToolTip("Folder containing RIP images to print (no subfolders)")
            self.browse_btn.setVisible(True)
            
            if hasattr(self, 'refresh_btn'):
                self.refresh_btn.setVisible(False)
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
        
        # Continuous Mode control
        self.continuous_mode.setVisible(settings.enable_continuous_mode)
        if not settings.enable_continuous_mode:
            self.continuous_mode.setChecked(False)
    
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
    
    def _execute_post_print_action(self, files_list: list):
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
                    self.status_log.append(f"✓ Post-print: Deleted {deleted_count} files")
            
            elif settings.post_print_action == "move":
                # Move files to destination
                if not settings.move_destination:
                    QMessageBox.warning(
                        self,
                        "Post-Print Error",
                        "Move destination not configured. Files were not moved."
                    )
                    return
                
                dest_path = Path(settings.move_destination)
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
                    error_msg = f"Moved {moved_count} files to {settings.move_destination}.\\n\\nFailed to move:\\n"
                    for file, error in failed_files[:5]:
                        error_msg += f"- {file}: {error}\\n"
                    if len(failed_files) > 5:
                        error_msg += f"... and {len(failed_files) - 5} more"
                    QMessageBox.warning(self, "Post-Print Move", error_msg)
                else:
                    self.status_log.append(f"✓ Post-print: Moved {moved_count} files to {settings.move_destination}")
        
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

            # LIMITATION: Skip logging for per-group mode (inaccurate file/copy counts)
            # TODO: Implement proper per-group logging that tracks actual printed files per group
            if self._using_per_group_mode:
                logging.info("Per-group mode logging skipped (approximate file counts)")
                self._print_job_files = []
                return

            logger = ProductionLogger()

            # Log each file that was printed
            for file_path_str in self._print_job_files:
                file_path = Path(file_path_str)
                filename = file_path.name

                # Log entry: server, filename, pages (assume 1), copies, mode
                logger.log_print_job(
                    server="Single",
                    filename=filename,
                    pages=1,  # Assume 1 page per file for now
                    copies=self._print_job_copies,
                    mode="Single"
                )

            # Clear tracked files after logging
            self._print_job_files = []

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
                # Check if user selected "don't show again" in this session
                if self._skip_reprint_warning_this_session:
                    return True  # Skip warning, proceed with print
                
                from PySide6.QtWidgets import QDialog
                dialog = ReprintWarningDialog(duplicates, self)
                result = dialog.exec()
                
                # Check if user selected "don't show again"
                if dialog.dont_show_again:
                    self._skip_reprint_warning_this_session = True
                
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
    
    def _record_to_history(self, files_list):
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
                server_name="Single",
                mode="Single",
                retention_days=settings.history_retention_days
            )
                
        except Exception as e:
            logging.error(f"Error recording to history: {e}")
            # Don't show error to user - history recording failure shouldn't interrupt workflow

