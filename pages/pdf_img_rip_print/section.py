from pathlib import Path
import os
import time
import logging

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QSpinBox, QComboBox, QCheckBox, QScrollArea, QTextEdit,
    QFileDialog, QProgressBar, QListWidget, QListWidgetItem
)
from PySide6.QtGui import QPixmap, QImage

from pages.pdf_to_image_converter.pdf_to_image_converter import PDFToImageConverter
from pages.images_to_rip.images_to_rip import ClientPool, ParallelImageRipProcessor
from pages.rip_to_print.rip_to_print import GISPrintServerClient, RIPFolderPrinter, natural_sort_key


logger = logging.getLogger(__name__)


def abort_print_server_operations(host='localhost', port=2000):
    try:
        from pages.rip_to_print.rip_to_print import GISPrintServerClient
        client = GISPrintServerClient(host, port)
        if not client.connect():
            return False
        ok = client.abort_print()
        client.close()
        return bool(ok)
    except Exception as e:
        logger.error(f"Abort print server error: {e}")
        return False


class PDFConversionWorker(QObject):
    finished = Signal()
    progress = Signal(int, str)
    error = Signal(str)

    def __init__(self, pdf_path: str, output_dir: str, dpi: int, rotation_deg: int):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.dpi = dpi
        self.rotation_deg = rotation_deg
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            converter = PDFToImageConverter(output_dir=self.output_dir, dpi=self.dpi, rotation_deg=self.rotation_deg)
            self.progress.emit(0, "Starting conversion...")
            # Convert with converter's own batching
            pdf_name = Path(self.pdf_path).name
            self.progress.emit(5, f"Converting {pdf_name}...")
            images = converter.convert_pdf_to_images(self.pdf_path)
            if self._cancelled:
                self.progress.emit(0, "Conversion cancelled")
                self.finished.emit()
                return
            self.progress.emit(100, f"Created {len(images)} images")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class ConversionBatchWorker(QObject):
    finished = Signal()
    progress = Signal(int, str)
    error = Signal(str)

    def __init__(self, folder_path: str, output_root: str, dpi: int, rotation_deg: int):
        super().__init__()
        self.folder_path = Path(folder_path)
        self.output_root = Path(output_root)
        self.dpi = dpi
        self.rotation_deg = rotation_deg
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if not self.folder_path.exists() or not self.folder_path.is_dir():
                self.error.emit("Folder not found")
                self.finished.emit()
                return

            pdf_files = sorted(self.folder_path.glob("*.pdf"))
            total = len(pdf_files)
            if total == 0:
                self.error.emit("No PDF files found in folder")
                self.finished.emit()
                return

            converter = PDFToImageConverter(output_dir=str(self.output_root), dpi=self.dpi, rotation_deg=self.rotation_deg)
            for idx, pdf_file in enumerate(pdf_files, start=1):
                if self._cancelled:
                    self.progress.emit(0, "Conversion cancelled")
                    break
                self.progress.emit(int((idx-1) * 100 / total), f"Converting {pdf_file.name} ({idx}/{total})...")
                converter.convert_pdf_to_images(str(pdf_file))
            if not self._cancelled:
                self.progress.emit(100, f"Converted {total} PDF(s)")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class SimpleRipWorker(QObject):
    finished = Signal(bool)
    error = Signal(str)
    progress = Signal(int, int, str)
    image_done = Signal(str)

    def __init__(self, input_folder: str, output_folder: str):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            SERVER_HOST = 'localhost'
            SERVER_PORT = 2000
            NUM_CONNECTIONS = 10     # Start higher (was 6)
            MAX_WORKERS = 8          # Start with 8 (was 6) 
            DELAY_BETWEEN_SUBMISSIONS = 0.20

            client_pool = ClientPool(SERVER_HOST, SERVER_PORT, pool_size=NUM_CONNECTIONS)
            if not client_pool.initialize():
                self.error.emit("Failed to connect to Print Server")
                self.finished.emit(False)
                return

            processor = ParallelImageRipProcessor(
                client_pool,
                output_dir=self.output_folder,
                max_workers=MAX_WORKERS
            )
            
            # Pass cancellation flag to processor
            processor.set_cancellation_callback(lambda: self._cancelled)
            
            # Set more aggressive cancellation checking
            processor.cancellation_callback = lambda: self._cancelled
            
            # Get total count first
            from pathlib import Path
            folder_path = Path(self.input_folder)
            image_files = []
            SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
            for file_path in folder_path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    image_files.append(file_path)
            total_count = len(image_files)
            
            # Monitor progress with worker count feedback
            import threading
            def monitor_progress():
                last_count = 0
                last_worker_count = MAX_WORKERS
                
                while not self._cancelled:  # Check cancellation first
                    if self._cancelled:  # Double check
                        processor.cancel_processing()
                        break
                        
                    current_count = processor.processed_count
                    current_workers = processor.get_current_worker_count()
                    
                    # Report worker count changes
                    if current_workers != last_worker_count:
                        self.progress.emit(current_count, total_count, 
                                         f"Processed {current_count}/{total_count} images (workers: {current_workers})")
                        last_worker_count = current_workers
                    elif current_count != last_count:
                        self.progress.emit(current_count, total_count, 
                                         f"Processed {current_count}/{total_count} images")
                    
                    last_count = current_count
                    
                    if current_count >= total_count:
                        break
                        
                    time.sleep(0.1)  # Check more frequently (was 0.5)
                
                # Ensure processor knows to stop if cancelled
                if self._cancelled:
                    processor.cancel_processing()
            
            monitor_thread = threading.Thread(target=monitor_progress)
            monitor_thread.start()
            
            # Process with cancellation support
            success = processor.process_folder_with_cancellation(
                self.input_folder,
                keep_structure=False,
                delay_between_submissions=DELAY_BETWEEN_SUBMISSIONS,
                cancellation_check=lambda: self._cancelled
            )
            
            monitor_thread.join(timeout=2)
            client_pool.close_all()
            self.finished.emit(success)
            
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)


class SequentialRipFoldersWorker(QObject):
    finished = Signal(bool)
    error = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, images_root: str, ripped_root: str):
        super().__init__()
        self.images_root = Path(images_root)
        self.ripped_root = Path(ripped_root)
        self._cancelled = False
        self.total_files_processed = 0

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if not self.images_root.exists():
                self.error.emit("Images root not found")
                self.finished.emit(False)
                return

            subfolders = sorted([p for p in self.images_root.iterdir() if p.is_dir()])
            total_folders = len(subfolders)
            if total_folders == 0:
                self.error.emit("No subfolders to RIP")
                self.finished.emit(False)
                return

            # Count total files across all folders first
            total_files_all_folders = 0
            SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
            folder_file_counts = {}  # Cache file counts
            
            for subfolder in subfolders:
                file_count = len([f for f in subfolder.rglob('*') 
                                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS])
                folder_file_counts[subfolder.name] = file_count
                total_files_all_folders += file_count

            if total_files_all_folders == 0:
                self.error.emit("No image files found in subfolders")
                self.finished.emit(False)
                return

            SERVER_HOST = 'localhost'
            SERVER_PORT = 2000
            NUM_CONNECTIONS = 12
            MAX_WORKERS = 12
            DELAY = 0.2

            client_pool = ClientPool(SERVER_HOST, SERVER_PORT, pool_size=NUM_CONNECTIONS)
            if not client_pool.initialize():
                self.error.emit("Failed to connect to Print Server")
                self.finished.emit(False)
                return

            success_all = True
            self.total_files_processed = 0

            for idx, sub in enumerate(subfolders, start=1):
                if self._cancelled:
                    success_all = False
                    break
                
                self.progress.emit(self.total_files_processed, total_files_all_folders, 
                                 f"Starting folder {sub.name} ({idx}/{total_folders})...")
                
                out_dir = self.ripped_root / sub.name
                out_dir.mkdir(parents=True, exist_ok=True)

                processor = ParallelImageRipProcessor(client_pool, output_dir=str(out_dir), max_workers=MAX_WORKERS)
                processor.set_cancellation_callback(lambda: self._cancelled)
                
                # Get current folder file count
                current_folder_files = folder_file_counts[sub.name]
                
                # Monitor this folder's progress
                import threading
                def monitor_folder_progress(folder_name=sub.name, base_processed=self.total_files_processed):
                    last_count = 0
                    while not self._cancelled and processor.processed_count < current_folder_files:
                        current_count = processor.processed_count
                        if current_count != last_count:
                            current_total = base_processed + current_count
                            self.progress.emit(current_total, total_files_all_folders,
                                             f"Processed {current_total}/{total_files_all_folders} images (folder: {folder_name})")
                            last_count = current_count
                        time.sleep(0.1)

                monitor_thread = threading.Thread(target=monitor_folder_progress)
                monitor_thread.start()

                # Process this folder
                ok = processor.process_folder_with_cancellation(
                    str(sub), 
                    keep_structure=False, 
                    delay_between_submissions=DELAY,
                    cancellation_check=lambda: self._cancelled
                )
                
                monitor_thread.join(timeout=2)
                
                # Update total processed count
                self.total_files_processed += current_folder_files
                
                if not ok or self._cancelled:
                    success_all = False
                    break

                time.sleep(0.2)

            client_pool.close_all()
            
            if not self._cancelled:
                self.progress.emit(total_files_all_folders, total_files_all_folders, 
                                 f"RIP sequence completed: {total_files_all_folders} files processed")
            
            self.finished.emit(success_all)
            
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)


class DirectPrintWorker(QObject):
    finished = Signal(bool)
    progress_update = Signal(int, int, str)
    status_update = Signal(str)
    files_discovered = Signal(int)  # Add this line
    
    def __init__(self, rip_folder, num_copies, continuous):
        super().__init__()
        self.rip_folder = rip_folder
        self.num_copies = num_copies
        self.continuous = continuous
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
    
    def run(self):
        try:
            from pages.rip_to_print.rip_to_print import GISPrintServerClient, RIPFolderPrinter
            
            client = GISPrintServerClient('localhost', 2000)
            if not client.connect():
                self.status_update.emit("Failed to connect to print server")
                self.finished.emit(False)
                return
            
            # Discover files first and emit count
            tmp_printer = RIPFolderPrinter(client)
            files_with_sizes = tmp_printer.discover_rip_files(self.rip_folder, "*.bmp", False)
            self.files_discovered.emit(len(files_with_sizes))
            
            def progress_cb(processed, total, message):
                if not self._cancelled:
                    self.progress_update.emit(processed, total, message)
            
            printer = RIPFolderPrinter(client, progress_cb)
            
            if self.continuous:
                success = printer.print_rip_folder_continuous(
                    self.rip_folder, num_copies=self.num_copies, max_wait_time=300
                )
            else:
                success = printer.print_rip_folder(
                    self.rip_folder, num_copies=self.num_copies
                )
            
            client.close()
            self.finished.emit(success and not self._cancelled)
            
        except Exception as e:
            self.status_update.emit(f"Print error: {e}")
            self.finished.emit(False)




class PDFImgRipPrintSection(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_preview_pdf = ""
        self._init_ui()
        # Initialize subfolder list with default folder
        self._refresh_subfolders()

    def _style_group_box(self, group_box):
        """Apply custom styling to group box titles to make them bigger and bold, positioned close to their own box with proper spacing between sections"""
        try:
            group_box.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    font-size: 12pt;
                    color: #212529;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    margin-top: 20px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0 8px;
                    background: transparent;
                    font-weight: bold;
                    font-size: 12pt;
                    color: #000000;
                }
            """)
        except Exception:
            pass

    def _init_ui(self):
        layout = QHBoxLayout(self)

        # Left controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(25)

        # PDF -> Images group
        pdf_group = QGroupBox("PDF to Images Conversion")
        self._style_group_box(pdf_group)
        pdf_v = QVBoxLayout()
        # Folder selection and listing
        folder_row = QHBoxLayout()
        self.pdf_folder_edit = QLineEdit()
        self.pdf_folder_edit.setPlaceholderText("Select a folder containing PDFs...")
        browse_pdf_folder = QPushButton("Browse Folder")
        browse_pdf_folder.clicked.connect(self._select_pdf_folder)
        folder_row.addWidget(self.pdf_folder_edit, 1)
        folder_row.addWidget(browse_pdf_folder)
        pdf_v.addLayout(folder_row)
        self.pdf_list = QListWidget()
        self.pdf_list.setMinimumHeight(100)
        pdf_v.addWidget(self.pdf_list)
        try:
            # Load preview on double click or when selection changes
            self.pdf_list.itemDoubleClicked.connect(lambda *_: self._load_selected_pdf_preview())
            self.pdf_list.currentRowChanged.connect(lambda *_: self._load_selected_pdf_preview())
        except Exception:
            pass
        load_preview_btn = QPushButton("Load Preview")
        load_preview_btn.clicked.connect(self._load_selected_pdf_preview)
        pdf_v.addWidget(load_preview_btn)
        # Single file selection
        row = QHBoxLayout()
        self.pdf_path_edit = QLineEdit()
        self.pdf_path_edit.setPlaceholderText("Select a PDF file...")
        browse_pdf = QPushButton("Browse PDF")
        browse_pdf.clicked.connect(self._select_pdf_file)
        row.addWidget(self.pdf_path_edit, 1)
        row.addWidget(browse_pdf)
        pdf_v.addLayout(row)
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("DPI:"))
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 1200)
        self.dpi_spin.setValue(360)
        try:
            self.dpi_spin.valueChanged.connect(self._update_pdf_preview)
        except Exception:
            pass
        dpi_row.addWidget(self.dpi_spin)
        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Rotation:"))
        self.rotation_combo = QComboBox()
        self.rotation_combo.addItems(["0°", "90°", "180°", "270°"])
        try:
            self.rotation_combo.currentIndexChanged.connect(self._update_pdf_preview)
        except Exception:
            pass
        rot_row.addWidget(self.rotation_combo)
        self.pdf_convert_btn = QPushButton("Convert PDF to Images")
        self.pdf_convert_btn.clicked.connect(self._start_pdf_conversion)
        pdf_v.addLayout(dpi_row)
        pdf_v.addLayout(rot_row)
        pdf_v.addWidget(self.pdf_convert_btn)
        pdf_group.setLayout(pdf_v)
        controls_layout.addWidget(pdf_group)

        # Images -> RIP group
        rip_group = QGroupBox("Images to RIP")
        self._style_group_box(rip_group)
        rip_v = QVBoxLayout()
        rip_row = QHBoxLayout()
        self.rip_input_edit = QLineEdit()
        # Default to consolidated images output path
        self.rip_input_edit.setText(str((Path('DATA') / 'consolidated' / 'images').resolve()))
        rip_browse = QPushButton("Browse")
        rip_browse.clicked.connect(self._select_rip_input_folder)
        rip_row.addWidget(self.rip_input_edit, 1)
        rip_row.addWidget(rip_browse)
        rip_v.addLayout(rip_row)

        # Add RIP progress bar
        self.rip_progress_bar = QProgressBar()
        self.rip_progress_bar.setVisible(False)
        self.rip_status_label = QLabel("Ready to start RIP")
        self.rip_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        rip_v.addWidget(self.rip_progress_bar)
        rip_v.addWidget(self.rip_status_label)

        self.rip_btn = QPushButton("Start RIP Processing")
        self.rip_btn.clicked.connect(self._start_rip_processing)
        self.rip_stop_btn = QPushButton("STOP")
        self.rip_stop_btn.setObjectName("StopButton")
        self.rip_stop_btn.setEnabled(False)
        self.rip_stop_btn.clicked.connect(self._stop_rip_processing)
        rip_v.addWidget(self.rip_btn)
        rip_v.addWidget(self.rip_stop_btn)
        rip_group.setLayout(rip_v)
        controls_layout.addWidget(rip_group)

        # Print RIP group
        print_group = QGroupBox("Preprocess the Folders")
        self._style_group_box(print_group)
        print_v = QVBoxLayout()
        pr_row = QHBoxLayout()
        self.print_folder_edit = QLineEdit()
        self.print_folder_edit.setText(str(Path('DATA/consolidated/ripped').resolve()))
        pr_browse = QPushButton("Browse")
        pr_browse.clicked.connect(self._select_print_folder)
        pr_row.addWidget(self.print_folder_edit, 1)
        pr_row.addWidget(pr_browse)
        print_v.addLayout(pr_row)
        
        # Subfolder list
        subfolder_row = QHBoxLayout()
        subfolder_row.addWidget(QLabel("Subfolders:"))
        refresh_subfolders_btn = QPushButton("🔄")
        refresh_subfolders_btn.setMaximumWidth(30)
        refresh_subfolders_btn.setToolTip("Refresh subfolder list")
        refresh_subfolders_btn.clicked.connect(self._refresh_subfolders)
        subfolder_row.addWidget(refresh_subfolders_btn)
        print_v.addLayout(subfolder_row)
        
        self.subfolder_list = QListWidget()
        self.subfolder_list.setMaximumHeight(120)
        self.subfolder_list.setDragDropMode(QListWidget.InternalMove)
        self.subfolder_list.setToolTip("Drag items to reorder subfolders for printing")
        print_v.addWidget(self.subfolder_list)
        
        # Preprocess button
        self.preprocess_btn = QPushButton("📁 Preprocess Folders")
        self.preprocess_btn.setToolTip("Create temp folder with sequentially ordered files")
        self.preprocess_btn.clicked.connect(self._preprocess_folders)
        print_v.addWidget(self.preprocess_btn)
        
        # Separate print folder selection
        print_folder_row = QHBoxLayout()
        print_folder_row.addWidget(QLabel("Print Folder:"))
        self.print_folder_for_printing_edit = QLineEdit()
        self.print_folder_for_printing_edit.setText(str((Path('DATA') / 'consolidated' / 'temp').resolve()))
        print_folder_browse_btn = QPushButton("Browse")
        print_folder_browse_btn.clicked.connect(self._select_print_folder_for_printing)
        print_folder_row.addWidget(self.print_folder_for_printing_edit, 1)
        print_folder_row.addWidget(print_folder_browse_btn)
        print_v.addLayout(print_folder_row)
        
        copies_row = QHBoxLayout()
        copies_row.addWidget(QLabel("Copies:"))
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 100)
        self.copies_spin.setValue(1)
        copies_row.addWidget(self.copies_spin)
        print_v.addLayout(copies_row)
        self.continuous_cb = QCheckBox("🔄 Continuous Mode")
        self.continuous_cb.setChecked(False)
        print_v.addWidget(self.continuous_cb)
        self.print_btn = QPushButton("Start Printing")
        self.print_btn.clicked.connect(self._start_printing)
        self.stop_btn = QPushButton("🛑 STOP PRINT SERVER")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_printing)
        print_v.addWidget(self.print_btn)
        print_v.addWidget(self.stop_btn)
        print_group.setLayout(print_v)
        controls_layout.addWidget(print_group)

        # Progress
        progress_group = QGroupBox("Progress")
        self._style_group_box(progress_group)
        pg_v = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        pg_v.addWidget(self.progress_bar)
        pg_v.addWidget(self.status_label)
        progress_group.setLayout(pg_v)
        controls_layout.addWidget(progress_group)

        controls_layout.addStretch(1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(controls_widget)
        left_scroll.setMinimumWidth(320)
        layout.addWidget(left_scroll, 3)

        # Right preview/status
        preview_widget = QWidget()
        preview_v = QVBoxLayout(preview_widget)
        preview_v.setSpacing(25)  # Add spacing between sections

        pdf_preview_group = QGroupBox("PDF Preview (First Page)")
        self._style_group_box(pdf_preview_group)
        pdf_preview_v = QVBoxLayout()
        self.preview_file_label = QLabel("No PDF selected")
        self.preview_file_label.setStyleSheet("color: #6c757d;")
        pdf_preview_v.addWidget(self.preview_file_label)
        self.preview_label = QLabel("No PDF selected")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("border: 1px solid #dee2e6; background-color: #f8f9fa; padding: 20px;")
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setMinimumHeight(300)
        pdf_preview_v.addWidget(self.preview_scroll)
        pdf_preview_group.setLayout(pdf_preview_v)
        preview_v.addWidget(pdf_preview_group)

        print_status_group = QGroupBox("Print Status")
        self._style_group_box(print_status_group)
        ps_v = QVBoxLayout()
        self.print_status_text = QTextEdit()
        self.print_status_text.setReadOnly(True)
        self.print_status_text.setMaximumHeight(150)
        self.print_status_text.setPlaceholderText("Print status and progress will appear here...")
        self.file_count_label = QLabel("Files to print: 0")
        self.file_count_label.setStyleSheet("font-weight: bold; color: #007bff;")
        ps_v.addWidget(self.print_status_text)
        ps_v.addWidget(self.file_count_label)
        print_status_group.setLayout(ps_v)
        preview_v.addWidget(print_status_group)

        server_info_group = QGroupBox("Print Server Information")
        self._style_group_box(server_info_group)
        si_v = QVBoxLayout()
        self.server_info_text = QTextEdit()
        self.server_info_text.setReadOnly(True)
        self.server_info_text.setMaximumHeight(100)
        self.server_info_text.setPlaceholderText("Print server connection status will appear here...")
        si_v.addWidget(self.server_info_text)
        server_info_group.setLayout(si_v)
        preview_v.addWidget(server_info_group)

        layout.addWidget(preview_widget, 7)
        layout.setStretch(0, 3)
        layout.setStretch(1, 7)

        # Output directories
        # PDF images output: DATA/consolidated/images
        self.pdf_output_dir = Path("DATA") / "consolidated" / "images"
        self.pdf_output_dir.mkdir(parents=True, exist_ok=True)
        # RIP output base: DATA/consolidated/ripped
        self.rip_output_dir = Path("DATA") / "consolidated" / "ripped"
        self.rip_output_dir.mkdir(parents=True, exist_ok=True)

    # --- Handlers ---
    def _select_pdf_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF", os.getcwd(), "PDF Files (*.pdf)")
        if file_path:
            self.pdf_path_edit.setText(file_path)
            self.current_preview_pdf = file_path
            self._update_pdf_preview()

    def _select_pdf_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select PDF Folder", os.getcwd())
        if folder:
            self.pdf_folder_edit.setText(folder)
            self.pdf_list.clear()
            try:
                pdfs = sorted(Path(folder).glob('*.pdf'))
                for p in pdfs:
                    item = QListWidgetItem(p.name)
                    item.setToolTip(str(p))
                    self.pdf_list.addItem(item)
                # Auto-select first and load preview
                if pdfs:
                    self.pdf_list.setCurrentRow(0)
                    self.current_preview_pdf = str(pdfs[0].resolve())
                    self._update_pdf_preview()
            except Exception:
                pass

    def _load_selected_pdf_preview(self):
        try:
            current = self.pdf_list.currentItem()
            if not current:
                return
            # Build absolute path robustly
            tip = current.toolTip()
            if tip and os.path.isabs(tip):
                path = tip
            else:
                folder = Path(self.pdf_folder_edit.text().strip())
                path = str((folder / current.text()).resolve())
            if not path or not os.path.exists(path):
                self.preview_file_label.setText("No PDF selected")
                self.preview_label.setText("No PDF selected or file not found")
                return
            self.current_preview_pdf = path
            self._update_pdf_preview()
        except Exception:
            pass

    def _update_pdf_preview(self):
        # Prefer a file chosen from the folder list if present
        pdf_path = (getattr(self, 'current_preview_pdf', '') or '').strip() or self.pdf_path_edit.text().strip()
        if not pdf_path or not os.path.exists(pdf_path):
            self.preview_label.setText("No PDF selected or file not found")
            self.preview_file_label.setText("No PDF selected")
            return
        try:
            import fitz
            dpi = int(self.dpi_spin.value())
            rotation_text = self.rotation_combo.currentText()
            rotation = int(rotation_text.replace('°', ''))
            self.preview_file_label.setText(os.path.basename(pdf_path))
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                self.preview_label.setText("Empty PDF")
                doc.close()
                return
            page = doc[0]
            mat = fitz.Matrix(dpi/72.0, dpi/72.0).prerotate(rotation)
            pix = page.get_pixmap(matrix=mat)
            if pix.alpha:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888)
            else:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            qimg = qimg.copy()
            pixmap = QPixmap.fromImage(qimg)
            max_w = self.preview_scroll.width() - 40
            max_h = self.preview_scroll.height() - 40
            if max_w > 0 and max_h > 0:
                pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_label.setPixmap(pixmap)
            doc.close()
        except Exception as e:
            self.preview_label.setText(f"Preview error: {e}")

    def _start_pdf_conversion(self):
        dpi = int(self.dpi_spin.value())
        rotation_text = self.rotation_combo.currentText()
        rotation = int(rotation_text.replace('°', ''))
        self.pdf_convert_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting PDF conversion...")

        folder = self.pdf_folder_edit.text().strip()
        if folder and os.path.isdir(folder):
            self.conv_thread = QThread()
            self.conv_worker = ConversionBatchWorker(folder, str(self.pdf_output_dir), dpi, rotation)
            self.conv_worker.moveToThread(self.conv_thread)
            self.conv_thread.started.connect(self.conv_worker.run)
            self.conv_worker.finished.connect(self.conv_thread.quit)
            self.conv_worker.finished.connect(self.conv_worker.deleteLater)
            self.conv_thread.finished.connect(self.conv_thread.deleteLater)
            self.conv_worker.progress.connect(self._on_conv_progress)
            self.conv_worker.error.connect(self._on_conv_error)
            self.conv_worker.finished.connect(self._on_conv_finished)
            self.conv_thread.start()
        else:
            pdf_path = self.pdf_path_edit.text().strip()
            if not pdf_path or not os.path.exists(pdf_path):
                self.status_label.setText("Select a PDF file or a folder")
                self.pdf_convert_btn.setEnabled(True)
                return
            self.conv_thread = QThread()
            self.conv_worker = PDFConversionWorker(pdf_path, str(self.pdf_output_dir), dpi, rotation)
            self.conv_worker.moveToThread(self.conv_thread)
            self.conv_thread.started.connect(self.conv_worker.run)
            self.conv_worker.finished.connect(self.conv_thread.quit)
            self.conv_worker.finished.connect(self.conv_worker.deleteLater)
            self.conv_thread.finished.connect(self.conv_thread.deleteLater)
            self.conv_worker.progress.connect(self._on_conv_progress)
            self.conv_worker.error.connect(self._on_conv_error)
            self.conv_worker.finished.connect(self._on_conv_finished)
            self.conv_thread.start()

    def _on_conv_progress(self, pct, msg):
        self.progress_bar.setValue(pct)
        self.status_label.setText(msg)

    def _on_conv_error(self, msg):
        self.status_label.setText(f"Error: {msg}")
        self.progress_bar.setValue(0)
        self._on_conv_finished()

    def _on_conv_finished(self):
        self.pdf_convert_btn.setEnabled(True)
        if self.progress_bar.value() == 100:
            self.progress_bar.setVisible(False)
            self.status_label.setText("Conversion completed successfully!")

    def _select_rip_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder", self.rip_input_edit.text())
        if folder:
            self.rip_input_edit.setText(folder)

    def _start_rip_processing(self):
        input_folder = self.rip_input_edit.text().strip()
        if not input_folder or not os.path.isdir(input_folder):
            return
        
        self.rip_btn.setEnabled(False)
        self.rip_stop_btn.setEnabled(True)
        self.rip_progress_bar.setVisible(True)
        self.rip_progress_bar.setValue(0)
        self.rip_status_label.setText("Starting RIP processing...")
        
        images_root = str((Path('DATA') / 'consolidated' / 'images').resolve())
        if os.path.abspath(input_folder) == os.path.abspath(images_root):
            # Use sequential processing for multiple folders
            self.rip_thread = QThread()
            self.rip_worker = SequentialRipFoldersWorker(images_root=images_root, ripped_root=str(self.rip_output_dir))
            self.rip_worker.moveToThread(self.rip_thread)
            self.rip_thread.started.connect(self.rip_worker.run)
            self.rip_worker.finished.connect(self.rip_thread.quit)
            self.rip_worker.finished.connect(self.rip_worker.deleteLater)
            self.rip_thread.finished.connect(self.rip_thread.deleteLater)
            self.rip_worker.progress.connect(self._on_rip_progress_simple)
            self.rip_worker.error.connect(self._on_rip_error)
            self.rip_worker.finished.connect(self._on_rip_finished)
            self.rip_thread.start()
        else:
            # Use enhanced single folder processing
            self.rip_thread = QThread()
            self.rip_worker = SimpleRipWorker(input_folder=input_folder, output_folder=str(self.rip_output_dir))
            self.rip_worker.moveToThread(self.rip_thread)
            self.rip_thread.started.connect(self.rip_worker.run)
            self.rip_worker.finished.connect(self.rip_thread.quit)
            self.rip_worker.finished.connect(self.rip_worker.deleteLater)
            self.rip_thread.finished.connect(self.rip_thread.deleteLater)
            self.rip_worker.progress.connect(self._on_rip_progress_detailed)
            self.rip_worker.error.connect(self._on_rip_error)
            self.rip_worker.finished.connect(self._on_rip_finished)
            self.rip_thread.start()

    def _stop_rip_processing(self):
        """Stop the RIP processing"""
        if hasattr(self, 'rip_worker') and self.rip_worker:
            self.rip_worker.cancel()
            self.rip_status_label.setText("Stopping RIP...")
            self.rip_stop_btn.setEnabled(False)
            
            # Force update the UI to show stopping status immediately
            from PySide6.QtCore import QCoreApplication
            QCoreApplication.processEvents()

    def _on_rip_progress_simple(self, processed, total, message):
        """Handle progress from SequentialRipFoldersWorker with individual file tracking"""
        try:
            if total > 0:
                percent = int((processed / total) * 100)
                self.rip_progress_bar.setValue(percent)
            else:
                self.rip_progress_bar.setValue(0)
            self.rip_status_label.setText(message)
        except Exception:
            pass

    def _on_rip_progress_detailed(self, processed, total, message):
        """Handle progress from SimpleRipWorker with regex extraction"""
        try:
            # Extract progress from messages like "Processed 150/6800 images"
            import re
            match = re.search(r'(\d+)/(\d+)', message)
            if match:
                current = int(match.group(1))
                total_files = int(match.group(2))
                percent = int((current / total_files) * 100)
                self.rip_progress_bar.setValue(percent)
            elif total > 0:
                percent = int((processed / total) * 100)
                self.rip_progress_bar.setValue(percent)
            else:
                self.rip_progress_bar.setValue(processed)
                
            self.rip_status_label.setText(message)
        except Exception:
            pass

    def _on_rip_error(self, msg):
        self.rip_status_label.setText(f"Error: {msg}")
        self.rip_progress_bar.setValue(0)
        self.rip_stop_btn.setEnabled(False)

    def _on_rip_finished(self, success):
        self.rip_btn.setEnabled(True)
        self.rip_stop_btn.setEnabled(False)
        if self.rip_progress_bar.value() == 100 and success:
            self.rip_status_label.setText("RIP completed successfully!")
            self.rip_progress_bar.setVisible(False)
        else:
            self.rip_status_label.setText("RIP stopped or completed with errors.")
            self.rip_progress_bar.setValue(0)

    def _select_print_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select RIP Folder", self.print_folder_edit.text())
        if folder:
            self.print_folder_edit.setText(folder)
            self._refresh_subfolders()

    def _select_print_folder_for_printing(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder for Printing", self.print_folder_for_printing_edit.text())
        if folder:
            self.print_folder_for_printing_edit.setText(folder)

    def _refresh_subfolders(self):
        """Refresh the subfolder list based on the selected print folder"""
        self.subfolder_list.clear()
        folder = self.print_folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            return
        
        try:
            folder_path = Path(folder)
            subfolders = [p for p in folder_path.iterdir() if p.is_dir()]
            subfolders.sort()  # Sort alphabetically by default
            
            for subfolder in subfolders:
                item = QListWidgetItem(subfolder.name)
                item.setToolTip(str(subfolder))
                self.subfolder_list.addItem(item)
        except Exception as e:
            logger.error(f"Error refreshing subfolders: {e}")

    def _preprocess_folders(self):
        """Preprocess folders by creating a temp folder with sequentially ordered files"""
        try:
            # Get the selected folder
            folder = self.print_folder_edit.text().strip()
            if not folder or not os.path.isdir(folder):
                self.status_label.setText("Please select a valid folder first")
                return
            
            # Get the order of subfolders from the list
            subfolder_names = []
            for i in range(self.subfolder_list.count()):
                item = self.subfolder_list.item(i)
                subfolder_names.append(item.text())
            
            if not subfolder_names:
                self.status_label.setText("No subfolders found to preprocess")
                return
            
            # Create temp folder path
            temp_folder = Path(folder) / "temp"
            
            # Clear existing temp folder if it exists
            if temp_folder.exists():
                import shutil
                shutil.rmtree(temp_folder)
            
            temp_folder.mkdir(parents=True, exist_ok=True)
            
            # Process files in order
            file_counter = 1
            total_files = 0
            
            # First, count total files
            for subfolder_name in subfolder_names:
                subfolder_path = Path(folder) / subfolder_name
                if subfolder_path.exists() and subfolder_path.is_dir():
                    bmp_files = list(subfolder_path.glob("*.bmp"))
                    total_files += len(bmp_files)
            
            if total_files == 0:
                self.status_label.setText("No BMP files found in subfolders")
                return
            
            self.status_label.setText(f"Preprocessing {total_files} files from {len(subfolder_names)} folders...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setMaximum(total_files)
            self.progress_bar.setValue(0)
            
            processed_files = 0
            
            # Process each subfolder in the specified order
            for subfolder_name in subfolder_names:
                subfolder_path = Path(folder) / subfolder_name
                if not subfolder_path.exists() or not subfolder_path.is_dir():
                    continue
                
                # Get all BMP files from this subfolder
                bmp_files = list(subfolder_path.glob("*.bmp"))
                bmp_files.sort(key=lambda x: natural_sort_key(str(x)))  # Sort within folder
                
                # Copy each file with sequential naming
                for bmp_file in bmp_files:
                    # Create new filename with sequential number
                    new_filename = f"{file_counter:03d}_{bmp_file.name}"
                    new_path = temp_folder / new_filename
                    
                    # Copy the file
                    import shutil
                    shutil.copy2(bmp_file, new_path)
                    
                    file_counter += 1
                    processed_files += 1
                    self.progress_bar.setValue(processed_files)
                    
                    # Update status
                    self.status_label.setText(f"Processed {processed_files}/{total_files} files...")
            
            # Update the print folder to temp folder
            self.print_folder_edit.setText(str(temp_folder))
            self.print_folder_for_printing_edit.setText(str(temp_folder))
            
            # Refresh subfolders (should be empty for temp folder)
            self._refresh_subfolders()
            
            self.progress_bar.setValue(total_files)
            self.status_label.setText(f"Preprocessing completed! Created {total_files} files in temp folder")
            
            logger.info(f"Preprocessing completed: {total_files} files processed into temp folder")
            
        except Exception as e:
            logger.error(f"Error during preprocessing: {e}")
            self.status_label.setText(f"Preprocessing failed: {e}")
            self.progress_bar.setValue(0)

    def _start_printing(self):
        rip_folder = self.print_folder_for_printing_edit.text().strip()
        if not rip_folder or not os.path.isdir(rip_folder):
            return
        
        num_copies = int(self.copies_spin.value())
        continuous = bool(self.continuous_cb.isChecked())
        
        self.print_status_text.clear()
        self.file_count_label.setText("Files to print: 0")
        self.print_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)  # Add this line
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting print process...")
        
        # Create and start worker thread
        self.print_thread = QThread()
        self.print_worker = DirectPrintWorker(rip_folder, num_copies, continuous)
        self.print_worker.moveToThread(self.print_thread)
        
        # Connect signals
        self.print_thread.started.connect(self.print_worker.run)
        self.print_worker.finished.connect(self.print_thread.quit)
        self.print_worker.finished.connect(self.print_worker.deleteLater)
        self.print_thread.finished.connect(self.print_thread.deleteLater)
        self.print_worker.progress_update.connect(self._on_print_progress)
        self.print_worker.status_update.connect(self._on_print_status)
        self.print_worker.files_discovered.connect(self._on_files_discovered)
        self.print_worker.finished.connect(self._on_print_finished)
        
        self.print_thread.start()

    def _stop_printing(self):
        if hasattr(self, 'print_worker') and self.print_worker:
            self.print_worker.cancel()
        self.status_label.setText("Stopping print process...")
        self.stop_btn.setEnabled(False)
        try:
            abort_print_server_operations('localhost', 2000)
        except Exception:
            pass
        self._on_print_finished(False)

    def _on_print_progress(self, processed, total, message):
        try:
            print(f"DEBUG: processed={processed}, total={total}, message='{message}'")  # Add this debug line
            
            if total > 0:
                percent = int((processed / total) * 100)
                self.progress_bar.setValue(percent)
                print(f"DEBUG: Setting progress bar to {percent}%")  # Add this debug line
            else:
                self.progress_bar.setValue(processed)
                print(f"DEBUG: Setting progress bar to {processed} (no total)")  # Add this debug line
                
            self.status_label.setText(message)
            timestamp = time.strftime("%H:%M:%S")
            self.print_status_text.append(f"[{timestamp}] {message}")
        except Exception as e:
            print(f"DEBUG: Error in _on_print_progress: {e}")  # Add this debug line
            pass

    def _on_print_status(self, message):
        self.status_label.setText(message)
        timestamp = time.strftime("%H:%M:%S")
        self.print_status_text.append(f"[{timestamp}] {message}")

    def _on_files_discovered(self, file_count):
        self.file_count_label.setText(f"Files to print: {file_count}")

    def _on_print_finished(self, success):
        self.print_btn.setEnabled(True) 
        self.stop_btn.setEnabled(False)
        if success:
            self.status_label.setText("Printing completed successfully!")
            self.progress_bar.setValue(100)
        else:
            self.status_label.setText("Printing failed or was cancelled")
            self.progress_bar.setValue(0)

    def _on_print_error(self, message):
        self.status_label.setText(f"Error: {message}")
        self.progress_bar.setValue(0)
        timestamp = time.strftime("%H:%M:%S")
        self.print_status_text.append(f"[{timestamp}] ERROR: {message}")

    def _on_connection_status(self, connected: bool, message: str):
        try:
            timestamp = time.strftime("%H:%M:%S")
            self.server_info_text.append(f"[{timestamp}] {message}")
        except Exception:
            pass
