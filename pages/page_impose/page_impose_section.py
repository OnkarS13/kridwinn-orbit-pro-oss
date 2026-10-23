import os
import io
import gc
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QFileDialog, QSpinBox, QMessageBox, QTextEdit, QProgressBar,
    QGridLayout, QCheckBox, QScrollArea
)
from PySide6.QtGui import QFont, QFontDatabase
import fitz  # PyMuPDF
from PIL import Image


class ProcessingThread(QThread):
    """Background thread for processing imposition without blocking GUI"""
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(str)
    error = Signal(str)
    ask_blank_pages = Signal(int, int, int)  # total_pages, pages_collation, blank_needed
    
    def __init__(self, params):
        super().__init__()
        self.params = params
        self.add_blank_pages = False
        self.blank_pages_response_received = False
        self.stop_requested = False
        
    def run(self):
        try:
            result = process_imposition(
                self.params['input_path'],
                self.params['output_path'],
                self.params['ups_width'],
                self.params['ups_length'],
                self.params['pages_collation'],
                self.params['array'],
                self.params['rotation_map'],
                self.params['margins'],
                self.params['reverse'],
                self.params['split_odd_even'],
                progress_callback=self.progress.emit,
                status_callback=self.status.emit,
                blank_pages_callback=self.handle_blank_pages,
                stop_check=lambda: self.stop_requested
            )
            # Emit finished signal with result (can be None if stopped)
            self.finished.emit(result if result else "")
        except Exception as e:
            import traceback
            error_detail = f"{str(e)}\n\n{traceback.format_exc()}"
            self.error.emit(error_detail)
    
    def handle_blank_pages(self, total_pages, pages_collation, blank_needed):
        """Called from process_imposition when blank pages are needed"""
        self.blank_pages_response_received = False
        self.ask_blank_pages.emit(total_pages, pages_collation, blank_needed)
        
        # Wait for response from main thread
        while not self.blank_pages_response_received:
            self.msleep(100)
        
        return self.add_blank_pages
    
    def set_blank_pages_response(self, add_pages):
        """Called by main thread with user's response"""
        self.add_blank_pages = add_pages
        self.blank_pages_response_received = True
    
    def request_stop(self):
        """Request the thread to stop processing"""
        self.stop_requested = True


def get_input_files(input_path):
    """Efficiently get all input files sorted"""
    input_files = []
    
    if os.path.isdir(input_path):
        valid_extensions = {'.pdf', '.png', '.jpg', '.jpeg'}
        for file in sorted(os.listdir(input_path)):
            if Path(file).suffix.lower() in valid_extensions:
                input_files.append(os.path.join(input_path, file))
    else:
        input_files = [input_path]
    
    return input_files


def count_pages_fast(file_path):
    """Fast page counting without validation"""
    if file_path.lower().endswith('.pdf'):
        doc = fitz.open(file_path)
        count = len(doc)
        first_page_size = None
        if count > 0:
            page = doc[0]
            first_page_size = (page.rect.width, page.rect.height)
        doc.close()
        return count, first_page_size, 'pdf'
    else:
        with Image.open(file_path) as img:
            return 1, (img.width, img.height), 'image'


def count_pages_and_validate(input_files, status_callback=None):
    """Parallel page counting for speed"""
    if status_callback:
        status_callback("Scanning files (parallel)...")
    
    total_pages = 0
    page_size = None
    
    # Use ThreadPoolExecutor for parallel file reading
    with ThreadPoolExecutor(max_workers=min(8, len(input_files))) as executor:
        results = list(executor.map(count_pages_fast, input_files))
    
    for idx, (count, size, ftype) in enumerate(results):
        total_pages += count
        if page_size is None:
            page_size = size
        elif not (abs(size[0] - page_size[0]) < 1 and abs(size[1] - page_size[1]) < 1):
            raise ValueError(f"Page size mismatch in {input_files[idx]}")
    
    return total_pages, page_size


def build_page_lookup(input_files, blank_pages_needed):
    """Build page lookup without reopening files"""
    page_lookup = []
    
    for file_path in input_files:
        if file_path.lower().endswith('.pdf'):
            # Quick count without loading
            doc = fitz.open(file_path)
            num_pages = len(doc)
            doc.close()
            
            for page_num in range(num_pages):
                page_lookup.append((file_path, page_num, 'pdf'))
        else:
            page_lookup.append((file_path, None, 'image'))
    
    for _ in range(blank_pages_needed):
        page_lookup.append((None, None, 'blank'))
    
    return page_lookup


def process_collation_batch(batch_start, batch_end, collation_params):
    """Process a batch of collations - can be called in separate thread"""
    try:
        page_lookup = collation_params['page_lookup']
        pages_collation = collation_params['pages_collation']
        output_pages_per_collation = collation_params['output_pages_per_collation']
        pages_per_sheet = collation_params['pages_per_sheet']
        array = collation_params['array']
        rotation_map = collation_params['rotation_map']
        sheet_width = collation_params['sheet_width']
        sheet_height = collation_params['sheet_height']
        page_width = collation_params['page_width']
        page_height = collation_params['page_height']
        margin_left = collation_params['margin_left']
        margin_top = collation_params['margin_top']
        page_width_with_margin = collation_params['page_width_with_margin']
        page_height_with_margin = collation_params['page_height_with_margin']
        ups_width = collation_params['ups_width']
        
        batch_doc = fitz.open()
        open_docs = {}
        
        try:
            for collation_idx in range(batch_start, batch_end):
                start_idx = collation_idx * pages_collation
                
                for output_page_idx in range(output_pages_per_collation):
                    new_page = batch_doc.new_page(width=sheet_width, height=sheet_height)
                    
                    start_pos = output_page_idx * pages_per_sheet
                    end_pos = start_pos + pages_per_sheet
                    
                    for i in range(start_pos, end_pos):
                        if i >= len(array):
                            continue
                        
                        page_num_in_collation = array[i] - 1
                        global_page_idx = start_idx + page_num_in_collation
                        
                        if global_page_idx >= len(page_lookup):
                            continue
                        
                        page_info = page_lookup[global_page_idx]
                        
                        # Get rotation for this page (based on its position in collation, 1-based)
                        page_position = page_num_in_collation + 1  # Convert to 1-based for rotation_map
                        rotation = rotation_map.get(page_position, 0)
                        
                        grid_row = (i - start_pos) // ups_width
                        grid_col = (i - start_pos) % ups_width
                        
                        x_pos = grid_col * page_width_with_margin + margin_left
                        y_pos = grid_row * page_height_with_margin + margin_top
                        
                        target_rect = fitz.Rect(x_pos, y_pos, 
                                               x_pos + page_width, 
                                               y_pos + page_height)
                        
                        if page_info[2] == 'blank':
                            continue
                        elif page_info[2] == 'pdf':
                            file_path = page_info[0]
                            page_num = page_info[1]
                            
                            if file_path not in open_docs:
                                open_docs[file_path] = fitz.open(file_path)
                            
                            src_doc = open_docs[file_path]
                            # Apply rotation when showing PDF page
                            new_page.show_pdf_page(target_rect, src_doc, page_num, rotate=rotation)
                        else:
                            file_path = page_info[0]
                            
                            with Image.open(file_path) as img:
                                # Apply rotation if needed (PIL uses opposite direction, so we rotate by the angle)
                                if rotation == 180:
                                    img = img.rotate(180, expand=False)
                                
                                if img.mode in ('RGBA', 'LA', 'P'):
                                    background = Image.new('RGB', img.size, (255, 255, 255))
                                    if img.mode == 'P':
                                        img = img.convert('RGBA')
                                    if 'A' in img.mode:
                                        background.paste(img, mask=img.split()[-1])
                                    else:
                                        background.paste(img)
                                    img = background
                                elif img.mode != 'RGB':
                                    img = img.convert('RGB')
                                
                                img_bytes = io.BytesIO()
                                img.save(img_bytes, format='JPEG', quality=85, optimize=True)
                                img_bytes.seek(0)
                                new_page.insert_image(target_rect, stream=img_bytes.read())
        
        finally:
            for doc in open_docs.values():
                doc.close()
            open_docs.clear()
        
        return batch_doc
        
    except Exception as e:
        import traceback
        print(f"Error in batch {batch_start}-{batch_end}: {e}")
        traceback.print_exc()
        raise


def process_imposition(input_path, output_path, ups_width, ups_length, 
                       pages_collation, array, rotation_map, margins, reverse, 
                       split_odd_even, progress_callback=None, 
                       status_callback=None, blank_pages_callback=None,
                       stop_check=None):
    """
    Optimized PDF imposition with batch processing and parallel file scanning
    """
    
    start_time = time.time()
    temp_files = []  # Track temp files for cleanup
    
    if status_callback:
        status_callback("Scanning input files...")
    
    input_files = get_input_files(input_path)
    
    if not input_files:
        raise ValueError("No valid PDF or image files found")
    
    # Check for stop before heavy processing
    if stop_check and stop_check():
        if status_callback:
            status_callback("Stopped by user")
        return None
    
    # Fast parallel validation
    total_input_pages, page_size = count_pages_and_validate(input_files, status_callback)
    
    if status_callback:
        status_callback(f"Found {total_input_pages} pages in {len(input_files)} files")
    
    pages_per_sheet = ups_width * ups_length
    check1 = pages_collation / pages_per_sheet
    if check1 != int(check1) or int(check1) % 2 != 0:
        raise ValueError(f"Pages/Collation ({pages_collation}) divided by "
                        f"(ups_width × ups_length = {pages_per_sheet}) must equal an even integer")
    
    remainder = total_input_pages % pages_collation
    blank_pages_needed = 0
    if remainder != 0:
        blank_pages_needed = pages_collation - remainder
        
        if blank_pages_callback:
            should_add = blank_pages_callback(total_input_pages, pages_collation, blank_pages_needed)
            if not should_add:
                raise ValueError("User cancelled: blank pages required")
    
    total_pages = total_input_pages + blank_pages_needed
    
    margin_left = margins['left'] * 72 / 25.4
    margin_right = margins['right'] * 72 / 25.4
    margin_top = margins['top'] * 72 / 25.4
    margin_bottom = margins['bottom'] * 72 / 25.4
    
    page_width = page_size[0]
    page_height = page_size[1]
    page_width_with_margin = page_width + margin_left + margin_right
    page_height_with_margin = page_height + margin_top + margin_bottom
    
    sheet_width = page_width_with_margin * ups_width
    sheet_height = page_height_with_margin * ups_length
    
    num_collations = total_pages // pages_collation
    output_pages_per_collation = int(check1)
    
    if status_callback:
        status_callback(f"Building page index for {num_collations} collations...")
    
    # Fast page lookup building
    page_lookup = build_page_lookup(input_files, blank_pages_needed)
    
    # Adaptive batch size based on total collations
    if num_collations <= 50:
        BATCH_SIZE = 10
    elif num_collations <= 200:
        BATCH_SIZE = 25
    elif num_collations <= 500:
        BATCH_SIZE = 50
    else:
        BATCH_SIZE = 100
    
    num_batches = (num_collations + BATCH_SIZE - 1) // BATCH_SIZE
    
    if status_callback:
        status_callback(f"Processing {num_collations} collations in {num_batches} batches (adaptive batch size: {BATCH_SIZE})...")
    
    # Prepare collation parameters
    collation_params = {
        'page_lookup': page_lookup,
        'pages_collation': pages_collation,
        'output_pages_per_collation': output_pages_per_collation,
        'pages_per_sheet': pages_per_sheet,
        'array': array,
        'rotation_map': rotation_map,
        'sheet_width': sheet_width,
        'sheet_height': sheet_height,
        'page_width': page_width,
        'page_height': page_height,
        'margin_left': margin_left,
        'margin_top': margin_top,
        'page_width_with_margin': page_width_with_margin,
        'page_height_with_margin': page_height_with_margin,
        'ups_width': ups_width
    }
    
    # Process batches sequentially but with optimized saves
    for batch_idx in range(num_batches):
        # Check for stop request
        if stop_check and stop_check():
            if status_callback:
                status_callback("Cleaning up and stopping...")
            # Clean up temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
            return None
        
        batch_start = batch_idx * BATCH_SIZE
        batch_end = min((batch_idx + 1) * BATCH_SIZE, num_collations)
        
        if status_callback:
            status_callback(f"Processing batch {batch_idx + 1}/{num_batches} (collations {batch_start + 1}-{batch_end})...")
        
        # Process batch
        batch_doc = process_collation_batch(batch_start, batch_end, collation_params)
        
        if progress_callback:
            progress_callback(int((batch_idx / num_batches) * 85))
        
        # Quick save without excessive cleanup
        if status_callback:
            status_callback(f"Saving batch {batch_idx + 1}/{num_batches}...")
        
        temp_path = output_path + f".temp_{batch_idx}.pdf"
        
        # Fast save - no garbage collection, just deflate
        batch_doc.save(temp_path, deflate=True, garbage=0)
        batch_doc.close()
        temp_files.append(temp_path)
        
        del batch_doc
        
        if batch_idx % 5 == 0:
            gc.collect()
        
        if progress_callback:
            progress_callback(int(((batch_idx + 1) / num_batches) * 85))
    
    if status_callback:
        status_callback("Merging batches...")
    
    if progress_callback:
        progress_callback(90)
    
    # Fast merge
    output_doc = fitz.open()
    
    for idx, temp_file in enumerate(temp_files):
        # Check for stop during merge
        if stop_check and stop_check():
            if status_callback:
                status_callback("Cleaning up and stopping...")
            output_doc.close()
            # Clean up remaining temp files
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
            return None
        
        temp_doc = fitz.open(temp_file)
        output_doc.insert_pdf(temp_doc)
        temp_doc.close()
        
        try:
            os.remove(temp_file)
        except:
            pass
        
        if progress_callback:
            progress_callback(90 + int((idx + 1) / len(temp_files) * 5))
    
    if status_callback:
        status_callback("Finalizing...")
    
    if reverse:
        if status_callback:
            status_callback("Reversing pages...")
        output_doc.select(list(reversed(range(len(output_doc)))))
    
    if progress_callback:
        progress_callback(96)
    
    if status_callback:
        status_callback("Saving final output...")
    
    if split_odd_even:
        base_name = os.path.splitext(output_path)[0]
        
        odd_doc = fitz.open()
        even_doc = fitz.open()
        
        for i in range(len(output_doc)):
            if i % 2 == 0:
                odd_doc.insert_pdf(output_doc, from_page=i, to_page=i)
            else:
                even_doc.insert_pdf(output_doc, from_page=i, to_page=i)
        
        odd_path = f"{base_name}_ODD.pdf"
        even_path = f"{base_name}_EVEN.pdf"
        
        odd_doc.save(odd_path, deflate=True, garbage=2)
        even_doc.save(even_path, deflate=True, garbage=2)
        odd_doc.close()
        even_doc.close()
        
        result_msg = f"Split complete!\nOdd: {odd_path}\nEven: {even_path}"
    else:
        output_doc.save(output_path, deflate=True, garbage=2)
        result_msg = f"Complete! Saved to: {output_path}"
    
    output_doc.close()
    
    elapsed = time.time() - start_time
    result_msg += f"\n\nProcessing time: {elapsed:.1f} seconds"
    
    if progress_callback:
        progress_callback(100)
    
    if status_callback:
        status_callback("Complete!")
    
    gc.collect()
    
    return result_msg


class PageImposeSection(QWidget):
    """
    PAGE IMPOSE section for PDF page imposition with threading support
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            self._ensure_google_sans()
        except Exception:
            pass
        
        self.output_folder = str(Path("FINAL_PDF_FOLDER").resolve())
        Path(self.output_folder).mkdir(parents=True, exist_ok=True)
        
        self.thread = None
        self._init_ui()
    
    def _ensure_google_sans(self):
        """Load Google Sans font if available"""
        try:
            font_path = Path("fonts/GoogleSans-Regular.ttf")
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))
        except Exception:
            pass
    
    def _style_group_box(self, group_box):
        """Apply consistent styling to group boxes"""
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 10pt;
                border: 2px solid #d1d5db;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                background-color: #f9fafb;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px;
                color: #374151;
            }
        """)
    
    def _init_ui(self):
        """Initialize the UI"""
        main_layout = QVBoxLayout(self)
        
        # Back button at the very top (outside scroll area)
        back_btn = QPushButton("← Back to Main Menu")
        back_btn.clicked.connect(self._back_to_pdf_desk)
        back_btn.setMaximumWidth(200)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: 600;
                padding: 8px 14px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        main_layout.addWidget(back_btn)
        
        # Create scroll area for the entire content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(15)
        
        # Title
        title_label = QLabel("PAGE IMPOSE")
        title_font = QFont("Google Sans", 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #1f2937; margin-bottom: 10px;")
        content_layout.addWidget(title_label)
        
        # Input/Output Section
        io_group = QGroupBox("Input/Output")
        self._style_group_box(io_group)
        io_layout = QGridLayout()
        io_layout.setSpacing(10)
        
        io_layout.addWidget(QLabel("Input (Folder/File):"), 0, 0)
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Select folder or file...")
        io_layout.addWidget(self.input_path, 0, 1)
        self.input_btn = QPushButton("Browse...")
        self.input_btn.clicked.connect(self.browse_input)
        io_layout.addWidget(self.input_btn, 0, 2)
        
        io_layout.addWidget(QLabel("Output Folder:"), 1, 0)
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setText(self.output_folder)
        io_layout.addWidget(self.output_folder_edit, 1, 1)
        self.output_folder_btn = QPushButton("Browse...")
        self.output_folder_btn.clicked.connect(self.browse_output_folder)
        io_layout.addWidget(self.output_folder_btn, 1, 2)
        
        io_layout.addWidget(QLabel("Output Filename:"), 2, 0)
        self.output_filename = QLineEdit()
        self.output_filename.setPlaceholderText("output.pdf")
        io_layout.addWidget(self.output_filename, 2, 1, 1, 2)
        
        io_group.setLayout(io_layout)
        content_layout.addWidget(io_group)
        
        # Parameters Section
        params_group = QGroupBox("Input Parameters")
        self._style_group_box(params_group)
        params_layout = QGridLayout()
        params_layout.setSpacing(10)
        
        params_layout.addWidget(QLabel("Ups/page (Width):"), 0, 0)
        self.ups_width = QSpinBox()
        self.ups_width.setRange(1, 10)
        self.ups_width.setValue(4)
        params_layout.addWidget(self.ups_width, 0, 1)
        
        params_layout.addWidget(QLabel("Ups/page (Length):"), 1, 0)
        self.ups_length = QSpinBox()
        self.ups_length.setRange(1, 10)
        self.ups_length.setValue(4)
        params_layout.addWidget(self.ups_length, 1, 1)
        
        params_layout.addWidget(QLabel("Pages/Collation:"), 2, 0)
        self.pages_collation = QSpinBox()
        self.pages_collation.setRange(1, 64)
        self.pages_collation.setValue(32)
        params_layout.addWidget(self.pages_collation, 2, 1)
        
        params_layout.addWidget(QLabel("ARRAY (comma-separated):"), 3, 0)
        self.array_input = QLineEdit()
        self.array_input.setPlaceholderText("e.g., 1,3,5,7,9,11,13,15,17,19,21,23,25,27,29,31,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32")
        params_layout.addWidget(self.array_input, 3, 1, 1, 2)
        
        params_group.setLayout(params_layout)
        content_layout.addWidget(params_group)
        
        # Page Rotation Section
        rotation_group = QGroupBox("Page Rotation (180°)")
        self._style_group_box(rotation_group)
        rotation_layout = QVBoxLayout()
        
        # Info label and helper buttons
        info_buttons_layout = QHBoxLayout()
        rotation_info = QLabel("Check pages that should be rotated 180° during imposition:")
        rotation_info.setStyleSheet("color: #6c757d; font-size: 9pt;")
        rotation_info.setWordWrap(True)
        info_buttons_layout.addWidget(rotation_info, 1)
        
        # Helper buttons
        select_all_btn = QPushButton("Select All")
        select_all_btn.setMaximumWidth(100)
        select_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                font-size: 9pt;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        select_all_btn.clicked.connect(self._select_all_rotations)
        info_buttons_layout.addWidget(select_all_btn)
        
        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setMaximumWidth(100)
        clear_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 9pt;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        clear_all_btn.clicked.connect(self._clear_all_rotations)
        info_buttons_layout.addWidget(clear_all_btn)
        
        rotation_layout.addLayout(info_buttons_layout)
        
        # Scroll area for checkboxes
        rotation_scroll = QScrollArea()
        rotation_scroll.setWidgetResizable(True)
        rotation_scroll.setMaximumHeight(200)
        rotation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Container for checkboxes
        self.rotation_checkbox_container = QWidget()
        self.rotation_checkbox_layout = QGridLayout(self.rotation_checkbox_container)
        self.rotation_checkbox_layout.setSpacing(8)
        self.rotation_checkboxes = []  # Will store checkbox references
        
        # Initially populate based on default Pages/Collation value
        self._populate_rotation_checkboxes()
        
        rotation_scroll.setWidget(self.rotation_checkbox_container)
        rotation_layout.addWidget(rotation_scroll)
        
        # Connect Pages/Collation spinbox to update checkboxes
        self.pages_collation.valueChanged.connect(self._populate_rotation_checkboxes)
        
        rotation_group.setLayout(rotation_layout)
        content_layout.addWidget(rotation_group)
        
        # Margins Section
        margins_group = QGroupBox("Margins (mm)")
        self._style_group_box(margins_group)
        margins_layout = QGridLayout()
        margins_layout.setSpacing(10)
        
        margins_layout.addWidget(QLabel("Top:"), 0, 0)
        self.margin_top = QSpinBox()
        self.margin_top.setRange(0, 100)
        self.margin_top.setValue(0)
        margins_layout.addWidget(self.margin_top, 0, 1)
        
        margins_layout.addWidget(QLabel("Bottom:"), 0, 2)
        self.margin_bottom = QSpinBox()
        self.margin_bottom.setRange(0, 100)
        self.margin_bottom.setValue(0)
        margins_layout.addWidget(self.margin_bottom, 0, 3)
        
        margins_layout.addWidget(QLabel("Left:"), 1, 0)
        self.margin_left = QSpinBox()
        self.margin_left.setRange(0, 100)
        self.margin_left.setValue(0)
        margins_layout.addWidget(self.margin_left, 1, 1)
        
        margins_layout.addWidget(QLabel("Right:"), 1, 2)
        self.margin_right = QSpinBox()
        self.margin_right.setRange(0, 100)
        self.margin_right.setValue(0)
        margins_layout.addWidget(self.margin_right, 1, 3)
        
        margins_group.setLayout(margins_layout)
        content_layout.addWidget(margins_group)
        
        # Output Options Section
        options_group = QGroupBox("Output Options")
        self._style_group_box(options_group)
        options_layout = QVBoxLayout()
        
        self.reverse_checkbox = QCheckBox("Reverse Output Order")
        options_layout.addWidget(self.reverse_checkbox)
        
        self.split_checkbox = QCheckBox("Split ODD/EVEN Pages")
        options_layout.addWidget(self.split_checkbox)
        
        options_group.setLayout(options_layout)
        content_layout.addWidget(options_group)
        
        # Status and Progress
        status_group = QGroupBox("Processing Status")
        self._style_group_box(status_group)
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("QLabel { color: #6b7280; font-style: italic; }")
        status_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                text-align: center;
                color: black;
            }
        """)
        status_layout.addWidget(self.progress_bar)
        
        status_group.setLayout(status_layout)
        content_layout.addWidget(status_group)
        
        # Process and Stop Buttons
        buttons_layout = QHBoxLayout()
        
        self.process_btn = QPushButton("Start Process of Imposition")
        self.process_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
        """)
        self.process_btn.clicked.connect(self.process)
        buttons_layout.addWidget(self.process_btn)
        
        self.stop_btn = QPushButton("Stop Process")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 12px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
            QPushButton:pressed {
                background-color: #b91c1c;
            }
            QPushButton:disabled {
                background-color: #9ca3af;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_process)
        self.stop_btn.setEnabled(False)
        buttons_layout.addWidget(self.stop_btn)
        
        content_layout.addLayout(buttons_layout)
        
        # Log Section
        log_group = QGroupBox("Log")
        self._style_group_box(log_group)
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        content_layout.addWidget(log_group)
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
    
    def _populate_rotation_checkboxes(self):
        """Dynamically create checkboxes based on Pages/Collation value"""
        # Clear existing checkboxes
        for checkbox in self.rotation_checkboxes:
            checkbox.deleteLater()
        self.rotation_checkboxes.clear()
        
        # Get current Pages/Collation value
        num_pages = self.pages_collation.value()
        
        # Create checkboxes in a grid (8 columns)
        cols = 8
        for i in range(num_pages):
            page_num = i + 1
            checkbox = QCheckBox(f"Page {page_num}")
            checkbox.setStyleSheet("font-size: 9pt;")
            
            row = i // cols
            col = i % cols
            self.rotation_checkbox_layout.addWidget(checkbox, row, col)
            self.rotation_checkboxes.append(checkbox)
    
    def _select_all_rotations(self):
        """Select all rotation checkboxes"""
        for checkbox in self.rotation_checkboxes:
            checkbox.setChecked(True)
    
    def _clear_all_rotations(self):
        """Clear all rotation checkboxes"""
        for checkbox in self.rotation_checkboxes:
            checkbox.setChecked(False)
    
    def browse_input(self):
        """Browse for input folder or file"""
        path = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Input PDF",
                "", "PDF Files (*.pdf);;Images (*.png *.jpg *.jpeg)"
            )
        if path:
            self.input_path.setText(path)
    
    def browse_output_folder(self):
        """Browse for output folder"""
        path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if path:
            self.output_folder_edit.setText(path)
    
    def _back_to_pdf_desk(self):
        """Return to PDF Desk main menu"""
        # Find the main application window
        parent_window = self.window()
        if hasattr(parent_window, '_switch_section'):
            # Switch to PDF Desk section (index 0)
            parent_window._switch_section(0)
    
    def log(self, message):
        """Add message to log"""
        self.log_text.append(message)
    
    def update_status(self, status):
        """Update status label and log"""
        self.status_label.setText(status)
        self.log(status)
    
    def validate_inputs(self):
        """Validate all input fields"""
        if not self.input_path.text():
            QMessageBox.warning(self, "Error", "Please select input folder/file")
            return False
        
        if not os.path.exists(self.input_path.text()):
            QMessageBox.warning(self, "Error", "Input path does not exist")
            return False
        
        if not self.output_folder_edit.text():
            QMessageBox.warning(self, "Error", "Please select output folder")
            return False
        
        if not os.path.exists(self.output_folder_edit.text()):
            QMessageBox.warning(self, "Error", "Output folder does not exist")
            return False
        
        if not self.output_filename.text():
            QMessageBox.warning(self, "Error", "Please enter output filename")
            return False
        
        if not self.output_filename.text().endswith('.pdf'):
            QMessageBox.warning(self, "Error", "Output filename must end with .pdf")
            return False
        
        array_text = self.array_input.text().strip()
        if not array_text:
            QMessageBox.warning(self, "Error", "Please enter ARRAY sequence")
            return False
        
        try:
            array = [int(x.strip()) for x in array_text.split(',')]
        except ValueError:
            QMessageBox.warning(self, "Error", "ARRAY must contain only numbers separated by commas")
            return False
        
        if len(array) != self.pages_collation.value():
            QMessageBox.warning(
                self, "Error",
                f"ARRAY length ({len(array)}) must match Pages/Collation ({self.pages_collation.value()})"
            )
            return False
        
        return True
    
    def process(self):
        """Start the imposition process in a background thread"""
        if not self.validate_inputs():
            return
        
        self.log("Starting imposition process...")
        self.process_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        array = [int(x.strip()) for x in self.array_input.text().split(',')]
        
        # Collect rotation data from checkboxes
        # rotation_map: dict mapping page number (1-based) to rotation angle (0 or 180)
        rotation_map = {}
        for i, checkbox in enumerate(self.rotation_checkboxes):
            page_num = i + 1
            rotation_map[page_num] = 180 if checkbox.isChecked() else 0
        
        output_path = os.path.join(self.output_folder_edit.text(), self.output_filename.text())
        
        params = {
            'input_path': self.input_path.text(),
            'output_path': output_path,
            'ups_width': self.ups_width.value(),
            'ups_length': self.ups_length.value(),
            'pages_collation': self.pages_collation.value(),
            'array': array,
            'rotation_map': rotation_map,  # Add rotation data
            'margins': {
                'top': self.margin_top.value(),
                'bottom': self.margin_bottom.value(),
                'left': self.margin_left.value(),
                'right': self.margin_right.value()
            },
            'reverse': self.reverse_checkbox.isChecked(),
            'split_odd_even': self.split_checkbox.isChecked()
        }
        
        self.thread = ProcessingThread(params)
        self.thread.progress.connect(self.update_progress)
        self.thread.status.connect(self.update_status)
        self.thread.finished.connect(self.on_finished)
        self.thread.error.connect(self.on_error)
        self.thread.ask_blank_pages.connect(self.on_ask_blank_pages)
        self.thread.start()
    
    def stop_process(self):
        """Stop the processing thread"""
        if self.thread and self.thread.isRunning():
            self.log("Stopping process...")
            self.status_label.setText("Stop requested, cleaning up...")
            self.thread.request_stop()
            self.stop_btn.setEnabled(False)
    
    def update_progress(self, value):
        """Update progress bar"""
        self.progress_bar.setValue(value)
    
    def on_ask_blank_pages(self, total_pages, pages_collation, blank_needed):
        """Ask user if they want to add blank pages"""
        response = QMessageBox.question(
            self, "Add Blank Pages?",
            f"Total pages ({total_pages}) is not divisible by Pages/Collation ({pages_collation}).\n"
            f"Need to add {blank_needed} blank pages to make total {total_pages + blank_needed} pages.\n\n"
            f"Continue with blank pages?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        self.thread.set_blank_pages_response(response == QMessageBox.Yes)
    
    def on_finished(self, message):
        """Handle successful completion"""
        if message:  # Empty string means stopped by user
            self.log(message)
            self.status_label.setText("Complete!")
            QMessageBox.information(self, "Success", message)
            self.progress_bar.setValue(100)
        else:
            self.log("Process stopped by user")
            self.status_label.setText("Stopped")
            self.progress_bar.setValue(0)
        self.process_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
    
    def on_error(self, error_msg):
        """Handle error"""
        self.log(f"ERROR: {error_msg}")
        self.status_label.setText("Error occurred")
        QMessageBox.critical(self, "Error", error_msg)
        self.process_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(0)
