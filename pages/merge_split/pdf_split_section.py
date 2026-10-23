import os
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor
import threading

from PySide6.QtCore import Qt, QThread, Signal, QObject, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QFileDialog, QSpinBox, QMessageBox, QListWidget, QListWidgetItem,
    QScrollArea, QTextEdit, QProgressBar, QSplitter, QRadioButton, QComboBox, QButtonGroup, QCheckBox,
    QTreeWidget, QTreeWidgetItem
)
from PySide6.QtGui import QPixmap, QImage, QFontDatabase, QFont, QIcon

# Import dimension checking functionality
from .single_pdf_dimension_worker import SinglePDFDimensionCheckWorker


class PDFSplitSection(QWidget):
    """
    UI section for PDF Desk - Merge and Split PDFs
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        try:
            self._ensure_google_sans()
        except Exception:
            pass
        
        # UI state
        self.current_mode = None  # None, 'merge', or 'split'
        self.folder_path = ""
        self.pdf_files_data = []  # List of dicts: {'name': str, 'path': str, 'pages': int, 'included': bool}
        self.output_folder = str(Path("FINAL_PDF_FOLDER").resolve())
        
        # Merge options
        self.merge_mode = "forward"  # forward, reverse, individual_reverse
        self.blank_page_mode = "none"  # none, alternative, end_of_final, end_of_each
        
        # UI containers that will be shown/hidden
        self.initial_buttons_container = None
        self.merge_container = None
        self.split_container = None
        
        # UI components
        self.pdf_list_widget = None
        self.progress_bar = None
        self.status_label = None
        
        self._init_ui()
        
        # Ensure output directory exists
        Path(self.output_folder).mkdir(parents=True, exist_ok=True)

    def _init_ui(self):
        """Initialize UI with main selection buttons"""
        main_layout = QVBoxLayout(self)
        
        # Create stacked containers
        self.initial_buttons_container = self._create_initial_buttons()
        self.merge_container = self._create_merge_ui()
        self.split_container = self._create_split_ui()
        
        # Add containers to main layout
        main_layout.addWidget(self.initial_buttons_container)
        main_layout.addWidget(self.merge_container)
        main_layout.addWidget(self.split_container)
        
        # Initially show only the buttons
        self.initial_buttons_container.setVisible(True)
        self.merge_container.setVisible(False)
        self.split_container.setVisible(False)

    def _create_initial_buttons(self):
        """Create the initial Merge, Split, and Page Impose buttons"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addStretch(2)
        
        # Center container for buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Merge button
        merge_btn = QPushButton("Merge")
        merge_btn.setMinimumSize(200, 80)
        merge_btn.setStyleSheet("""
            QPushButton {
                font-size: 18pt;
                font-weight: bold;
                background-color: #007bff;
                color: white;
                border-radius: 10px;
                padding: 20px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        merge_btn.clicked.connect(self._show_merge_ui)
        button_layout.addWidget(merge_btn)
        
        button_layout.addSpacing(40)
        
        # Split button
        split_btn = QPushButton("Split")
        split_btn.setMinimumSize(200, 80)
        split_btn.setStyleSheet("""
            QPushButton {
                font-size: 18pt;
                font-weight: bold;
                background-color: #007bff;
                color: white;
                border-radius: 10px;
                padding: 20px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        split_btn.clicked.connect(self._show_split_ui)
        button_layout.addWidget(split_btn)
        
        button_layout.addSpacing(40)
        
        # Organizer button
        page_impose_btn = QPushButton("Organizer")
        page_impose_btn.setMinimumSize(200, 80)
        page_impose_btn.setStyleSheet("""
            QPushButton {
                font-size: 18pt;
                font-weight: bold;
                background-color: #007bff;
                color: white;
                border-radius: 10px;
                padding: 20px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        page_impose_btn.clicked.connect(self._open_page_impose)
        button_layout.addWidget(page_impose_btn)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        layout.addStretch(3)
        
        return container

    def _create_merge_ui(self):
        """Create the merge UI (shown when Merge button is clicked)"""
        container = QWidget()
        main_layout = QVBoxLayout(container)
        
        # Back button
        back_btn = QPushButton("← Back to Main Menu")
        back_btn.clicked.connect(self._show_initial_buttons)
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
        
        # Main content area with scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)
        
        # 1. Input Folder Selection
        folder_group = QGroupBox("Input Folder")
        self._style_group_box(folder_group)
        folder_layout = QHBoxLayout()
        self.merge_folder_edit = QLineEdit()
        self.merge_folder_edit.setPlaceholderText("Select folder containing PDFs...")
        self.merge_folder_edit.setReadOnly(True)
        folder_layout.addWidget(self.merge_folder_edit, 1)
        browse_folder_btn = QPushButton("Browse Folder")
        browse_folder_btn.setObjectName("browse_folder_btn")  # Add this line
        browse_folder_btn.clicked.connect(self._browse_merge_folder)
        folder_layout.addWidget(browse_folder_btn)
        folder_group.setLayout(folder_layout)
        content_layout.addWidget(folder_group)
        
        # 2. PDF List with page counts and remove buttons
        pdf_list_group = QGroupBox("PDFs to Merge")
        self._style_group_box(pdf_list_group)
        pdf_list_layout = QVBoxLayout()
        
        # Info label
        info_label = QLabel("Select which PDFs to include and set their order (drag to reorder):")
        info_label.setStyleSheet("color: #6c757d; font-size: 9pt;")
        info_label.setWordWrap(True)
        pdf_list_layout.addWidget(info_label)
        
        # Custom PDF list widget
        self.pdf_list_widget = QListWidget()
        self.pdf_list_widget.setDragDropMode(QListWidget.InternalMove)
        self.pdf_list_widget.setMinimumHeight(200)
        self.pdf_list_widget.model().rowsMoved.connect(self._on_pdf_order_changed)
        pdf_list_layout.addWidget(self.pdf_list_widget)
        
        # Dimensions result label (populated after folder browse)
        self.merge_dim_label = QLabel("")
        self.merge_dim_label.setStyleSheet("color: #495057; font-size: 9pt;")
        self.merge_dim_label.setWordWrap(True)
        pdf_list_layout.addWidget(self.merge_dim_label)
        
        pdf_list_group.setLayout(pdf_list_layout)
        content_layout.addWidget(pdf_list_group)
        
        # 3. Merge Options
        merge_options_group = QGroupBox("Merge Options")
        self._style_group_box(merge_options_group)
        merge_options_layout = QVBoxLayout()
        
        # Radio buttons for merge mode
        self.merge_mode_group = QButtonGroup()
        
        self.forward_merge_radio = QRadioButton("Forward Merge (normal sequential merge)")
        self.forward_merge_radio.setChecked(True)
        self.forward_merge_radio.toggled.connect(lambda: self._set_merge_mode("forward"))
        self.merge_mode_group.addButton(self.forward_merge_radio)
        merge_options_layout.addWidget(self.forward_merge_radio)
        
        self.reverse_merge_radio = QRadioButton("Reverse Merge (entire merged PDF reversed)")
        self.reverse_merge_radio.toggled.connect(lambda: self._set_merge_mode("reverse"))
        self.merge_mode_group.addButton(self.reverse_merge_radio)
        merge_options_layout.addWidget(self.reverse_merge_radio)
        
        self.individual_reverse_radio = QRadioButton("Individual Reverse Merge (reverse each PDF individually, then merge)")
        self.individual_reverse_radio.toggled.connect(lambda: self._set_merge_mode("individual_reverse"))
        self.merge_mode_group.addButton(self.individual_reverse_radio)
        merge_options_layout.addWidget(self.individual_reverse_radio)
        
        merge_options_group.setLayout(merge_options_layout)
        content_layout.addWidget(merge_options_group)
        
        # 4. Blank Page Options
        blank_page_group = QGroupBox("Add Blank Pages")
        self._style_group_box(blank_page_group)
        blank_page_layout = QVBoxLayout()
        
        blank_page_label = QLabel("Blank page insertion:")
        blank_page_layout.addWidget(blank_page_label)
        
        self.blank_page_combo = QComboBox()
        self.blank_page_combo.addItems([
            "No blank pages",
            "Add blank pages alternatively",
            "Add blank page at end of final merged PDF",
            "Add blank page at end of each PDF"
        ])
        self.blank_page_combo.currentIndexChanged.connect(self._on_blank_page_option_changed)
        blank_page_layout.addWidget(self.blank_page_combo)
        
        blank_page_group.setLayout(blank_page_layout)
        content_layout.addWidget(blank_page_group)
        
        # 5. Output Settings
        output_group = QGroupBox("Output Settings")
        self._style_group_box(output_group)
        output_layout = QVBoxLayout()
        
        # Output folder
        output_folder_layout = QHBoxLayout()
        output_folder_layout.addWidget(QLabel("Output Folder:"))
        self.merge_output_folder_edit = QLineEdit()
        self.merge_output_folder_edit.setText(self.output_folder)
        self.merge_output_folder_edit.setReadOnly(True)
        output_folder_layout.addWidget(self.merge_output_folder_edit, 1)
        browse_output_btn = QPushButton("Browse")
        browse_output_btn.clicked.connect(self._browse_output_folder)
        output_folder_layout.addWidget(browse_output_btn)
        output_layout.addLayout(output_folder_layout)
        
        # Output filename
        output_name_layout = QHBoxLayout()
        output_name_layout.addWidget(QLabel("File Name:"))
        self.merge_output_name_edit = QLineEdit()
        self.merge_output_name_edit.setPlaceholderText("Enter output PDF name...")
        self.merge_output_name_edit.setText("Merged_Document")
        self.merge_output_name_edit.textChanged.connect(self._update_merge_button_state)
        output_name_layout.addWidget(self.merge_output_name_edit, 1)
        output_layout.addLayout(output_name_layout)
        
        output_group.setLayout(output_layout)
        content_layout.addWidget(output_group)
        
        # 6. Start Button
        self.merge_start_btn = QPushButton("Start Merge")
        self.merge_start_btn.setMinimumHeight(50)
        self.merge_start_btn.setStyleSheet("""
            QPushButton {
                font-size: 14pt;
                font-weight: bold;
                background-color: #007bff;
                color: white;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.merge_start_btn.clicked.connect(self._start_merge_process)
        self.merge_start_btn.setEnabled(False)
        content_layout.addWidget(self.merge_start_btn)
        
        # Stop button
        self.merge_stop_btn = QPushButton("STOP")
        self.merge_stop_btn.setMinimumHeight(50)
        self.merge_stop_btn.setStyleSheet("""
            QPushButton {
                font-size: 14pt;
                font-weight: bold;
                background-color: #dc3545;
                color: white;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.merge_stop_btn.clicked.connect(self._stop_merge_process)
        self.merge_stop_btn.setEnabled(False)  # Initially disabled
        content_layout.addWidget(self.merge_stop_btn)
        
        # 7. Progress and Status
        progress_group = QGroupBox("Progress")
        self._style_group_box(progress_group)
        progress_layout = QVBoxLayout()
        
        # Scanning progress bar (for folder scanning)
        self.merge_scan_progress_bar = QProgressBar()
        self.merge_scan_progress_bar.setVisible(False)
        progress_layout.addWidget(self.merge_scan_progress_bar)
        
        # Merge progress bar (for actual merging)
        self.merge_progress_bar = QProgressBar()
        self.merge_progress_bar.setVisible(False)
        progress_layout.addWidget(self.merge_progress_bar)
        
        self.merge_status_label = QLabel("Ready")
        self.merge_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        progress_layout.addWidget(self.merge_status_label)
        
        progress_group.setLayout(progress_layout)
        content_layout.addWidget(progress_group)
        
        # 8. Preview Section (EXPANDED)
        preview_group = QGroupBox("Preview - Merged PDFs")
        self._style_group_box(preview_group)
        preview_main_layout = QHBoxLayout()
        
        # Left side: List of merged PDFs (smaller width)
        pdf_list_container = QWidget()
        pdf_list_container_layout = QVBoxLayout(pdf_list_container)
        pdf_list_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Refresh button
        refresh_layout = QHBoxLayout()
        refresh_label = QLabel("Merged PDFs:")
        refresh_label.setStyleSheet("font-weight: bold; color: #212529;")
        refresh_layout.addWidget(refresh_label)
        self.refresh_preview_btn = QPushButton("Refresh")
        self.refresh_preview_btn.setMaximumWidth(100)
        self.refresh_preview_btn.clicked.connect(self._refresh_merged_pdfs_list)
        refresh_layout.addWidget(self.refresh_preview_btn)
        pdf_list_container_layout.addLayout(refresh_layout)
        
        # List of merged PDFs (taller)
        self.merged_pdfs_list = QListWidget()
        self.merged_pdfs_list.setMinimumHeight(500)  # Increased from 200
        self.merged_pdfs_list.itemClicked.connect(self._on_merged_pdf_selected)
        pdf_list_container_layout.addWidget(self.merged_pdfs_list)
        
        preview_main_layout.addWidget(pdf_list_container, 1)  # 1 part width
        
        # Right side: Preview of selected PDF (larger width)
        preview_container = QWidget()
        preview_container_layout = QVBoxLayout(preview_container)
        preview_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # PDF info label (bigger font)
        self.preview_pdf_info_label = QLabel("Select a PDF to preview")
        self.preview_pdf_info_label.setStyleSheet("font-weight: bold; color: #007bff; padding: 10px; font-size: 11pt;")
        self.preview_pdf_info_label.setAlignment(Qt.AlignCenter)
        self.preview_pdf_info_label.setWordWrap(True)
        preview_container_layout.addWidget(self.preview_pdf_info_label)
        
        # Preview scroll area (much taller)
        self.merged_pdf_preview_scroll = QScrollArea()
        self.merged_pdf_preview_scroll.setWidgetResizable(True)
        self.merged_pdf_preview_scroll.setMinimumHeight(600)  # Increased from 300
        self.merged_pdf_preview_label = QLabel("No preview available")
        self.merged_pdf_preview_label.setAlignment(Qt.AlignCenter)
        self.merged_pdf_preview_label.setStyleSheet("""
    border: 2px solid #dee2e6; 
    background-color: #f8f9fa; 
    padding: 20px;
    font-size: 10pt;
    color: #6c757d;
""")
        self.merged_pdf_preview_scroll.setWidget(self.merged_pdf_preview_label)
        preview_container_layout.addWidget(self.merged_pdf_preview_scroll)
        
        preview_main_layout.addWidget(preview_container, 3)  # 3 parts width (bigger)
        
        preview_group.setLayout(preview_main_layout)
        content_layout.addWidget(preview_group)
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        return container

    def _create_split_ui(self):
        """Create the split UI with full functionality"""
        container = QWidget()
        main_layout = QVBoxLayout(container)
        
        # Back button
        back_btn = QPushButton("← Back to Main Menu")
        back_btn.clicked.connect(self._show_initial_buttons)
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
        
        # Main content area with scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)
        
        # 1. Input PDF Selection
        input_group = QGroupBox("Input PDF File")
        self._style_group_box(input_group)
        input_layout = QVBoxLayout()
        
        file_layout = QHBoxLayout()
        self.split_pdf_edit = QLineEdit()
        self.split_pdf_edit.setPlaceholderText("Select a PDF file to split...")
        self.split_pdf_edit.setReadOnly(True)
        file_layout.addWidget(self.split_pdf_edit, 1)
        
        browse_pdf_btn = QPushButton("Browse PDF")
        browse_pdf_btn.setObjectName("split_browse_pdf_btn")
        browse_pdf_btn.clicked.connect(self._browse_split_pdf)
        file_layout.addWidget(browse_pdf_btn)
        input_layout.addLayout(file_layout)
        
        # PDF info label
        self.split_pdf_info_label = QLabel("No PDF selected")
        self.split_pdf_info_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 5px;")
        input_layout.addWidget(self.split_pdf_info_label)
        
        input_group.setLayout(input_layout)
        content_layout.addWidget(input_group)
        
        # 2. Split Options
        split_options_group = QGroupBox("Split Options")
        self._style_group_box(split_options_group)
        split_options_layout = QVBoxLayout()
        
        # Radio buttons for split mode
        self.split_mode_group = QButtonGroup()
        
        # Range-based split
        self.range_split_radio = QRadioButton("Range-based split (specify pages per file)")
        self.range_split_radio.setChecked(True)
        self.split_mode_group.addButton(self.range_split_radio)
        split_options_layout.addWidget(self.range_split_radio)
        
        # Range input
        range_input_layout = QHBoxLayout()
        range_input_layout.addSpacing(30)
        range_input_layout.addWidget(QLabel("Pages per split:"))
        self.pages_per_split_spin = QSpinBox()
        self.pages_per_split_spin.setRange(1, 10000)
        self.pages_per_split_spin.setValue(10)
        self.pages_per_split_spin.setMaximumWidth(100)
        range_input_layout.addWidget(self.pages_per_split_spin)
        range_input_layout.addStretch()
        split_options_layout.addLayout(range_input_layout)
        
        # Odd/Even split
        self.odd_even_split_radio = QRadioButton("Odd and Even pages split (creates 2 PDFs)")
        self.split_mode_group.addButton(self.odd_even_split_radio)
        split_options_layout.addWidget(self.odd_even_split_radio)
        
        # ADD THIS: Custom ranges split
        self.custom_ranges_radio = QRadioButton("Custom ranges (specify multiple page ranges)")
        self.split_mode_group.addButton(self.custom_ranges_radio)
        split_options_layout.addWidget(self.custom_ranges_radio)
        
        # Custom ranges input
        custom_ranges_input_layout = QVBoxLayout()
        custom_ranges_input_layout.addSpacing(10)
        
        # Range entry controls
        range_entry_layout = QHBoxLayout()
        range_entry_layout.addSpacing(30)
        range_entry_layout.addWidget(QLabel("From page:"))
        self.custom_range_from_spin = QSpinBox()
        self.custom_range_from_spin.setRange(1, 100000)
        self.custom_range_from_spin.setValue(1)
        self.custom_range_from_spin.setMaximumWidth(80)
        range_entry_layout.addWidget(self.custom_range_from_spin)
        
        range_entry_layout.addWidget(QLabel("To page:"))
        self.custom_range_to_spin = QSpinBox()
        self.custom_range_to_spin.setRange(1, 100000)
        self.custom_range_to_spin.setValue(1)
        self.custom_range_to_spin.setMaximumWidth(80)
        range_entry_layout.addWidget(self.custom_range_to_spin)
        
        self.add_range_btn = QPushButton("Add Range")
        self.add_range_btn.setMaximumWidth(100)
        self.add_range_btn.clicked.connect(self._add_custom_range)
        range_entry_layout.addWidget(self.add_range_btn)
        
        range_entry_layout.addStretch()
        custom_ranges_input_layout.addLayout(range_entry_layout)
        
        # List of added ranges
        ranges_list_layout = QHBoxLayout()
        ranges_list_layout.addSpacing(30)
        ranges_list_layout.addWidget(QLabel("Added ranges:"))
        self.custom_ranges_list = QListWidget()
        self.custom_ranges_list.setMaximumHeight(100)
        ranges_list_layout.addWidget(self.custom_ranges_list, 1)
        
        # Remove and Clear buttons
        ranges_buttons_layout = QVBoxLayout()
        self.remove_range_btn = QPushButton("Remove")
        self.remove_range_btn.setMaximumWidth(80)
        self.remove_range_btn.clicked.connect(self._remove_custom_range)
        ranges_buttons_layout.addWidget(self.remove_range_btn)
        
        self.clear_ranges_btn = QPushButton("Clear All")
        self.clear_ranges_btn.setMaximumWidth(80)
        self.clear_ranges_btn.clicked.connect(self._clear_custom_ranges)
        ranges_buttons_layout.addWidget(self.clear_ranges_btn)
        ranges_buttons_layout.addStretch()
        ranges_list_layout.addLayout(ranges_buttons_layout)
        
        custom_ranges_input_layout.addLayout(ranges_list_layout)
        
        split_options_layout.addLayout(custom_ranges_input_layout)
        
        split_options_group.setLayout(split_options_layout)
        content_layout.addWidget(split_options_group)
        
        # 3. Additional Options
        additional_options_group = QGroupBox("Additional Options")
        self._style_group_box(additional_options_group)
        additional_options_layout = QVBoxLayout()
        
        # Add blank page option
        self.split_add_blank_checkbox = QCheckBox("Add blank page at end of each split PDF")
        self.split_add_blank_checkbox.setChecked(False)
        additional_options_layout.addWidget(self.split_add_blank_checkbox)
        
        # Reverse split option
        self.split_reverse_checkbox = QCheckBox("Reverse split (save split PDFs in reverse order)")
        self.split_reverse_checkbox.setChecked(False)
        additional_options_layout.addWidget(self.split_reverse_checkbox)
        
        additional_options_group.setLayout(additional_options_layout)
        content_layout.addWidget(additional_options_group)
        
        # 4. Output Settings
        output_group = QGroupBox("Output Settings")
        self._style_group_box(output_group)
        output_layout = QVBoxLayout()
        
        # Output folder
        output_folder_layout = QHBoxLayout()
        output_folder_layout.addWidget(QLabel("Output Folder:"))
        self.split_output_folder_edit = QLineEdit()
        self.split_output_folder_edit.setText(self.output_folder)
        self.split_output_folder_edit.setReadOnly(True)
        output_folder_layout.addWidget(self.split_output_folder_edit, 1)
        browse_output_btn = QPushButton("Browse")
        browse_output_btn.clicked.connect(self._browse_split_output_folder)
        output_folder_layout.addWidget(browse_output_btn)
        output_layout.addLayout(output_folder_layout)
        
        # Base filename for splits
        output_name_layout = QHBoxLayout()
        output_name_layout.addWidget(QLabel("Base File Name:"))
        self.split_output_name_edit = QLineEdit()
        self.split_output_name_edit.setPlaceholderText("Base name for split PDFs...")
        self.split_output_name_edit.setText("Split_PDF")
        self.split_output_name_edit.textChanged.connect(self._update_split_button_state)  # ADD THIS
        output_name_layout.addWidget(self.split_output_name_edit, 1)
        output_layout.addLayout(output_name_layout)
        
        # Info label
        naming_info = QLabel("Split PDFs will be named: [BaseName]_part_1.pdf, [BaseName]_part_2.pdf, etc.")
        naming_info.setStyleSheet("color: #6c757d; font-size: 9pt; padding: 5px;")
        naming_info.setWordWrap(True)
        output_layout.addWidget(naming_info)
        
        output_group.setLayout(output_layout)
        content_layout.addWidget(output_group)
        
        # 5. Start and Stop Buttons
        self.split_start_btn = QPushButton("Start Split")
        self.split_start_btn.setMinimumHeight(50)
        self.split_start_btn.setStyleSheet("""
            QPushButton {
                font-size: 14pt;
                font-weight: bold;
                background-color: #28a745;
                color: white;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.split_start_btn.clicked.connect(self._start_split_process)
        self.split_start_btn.setEnabled(False)
        content_layout.addWidget(self.split_start_btn)
        
        self.split_stop_btn = QPushButton("STOP")
        self.split_stop_btn.setMinimumHeight(50)
        self.split_stop_btn.setStyleSheet("""
            QPushButton {
                font-size: 14pt;
                font-weight: bold;
                background-color: #dc3545;
                color: white;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.split_stop_btn.clicked.connect(self._stop_split_process)
        self.split_stop_btn.setEnabled(False)
        content_layout.addWidget(self.split_stop_btn)
        
        # 6. Progress and Status
        progress_group = QGroupBox("Progress")
        self._style_group_box(progress_group)
        progress_layout = QVBoxLayout()
        
        self.split_progress_bar = QProgressBar()
        self.split_progress_bar.setVisible(False)
        progress_layout.addWidget(self.split_progress_bar)
        
        self.split_status_label = QLabel("Ready to split")
        self.split_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        progress_layout.addWidget(self.split_status_label)
        
        progress_group.setLayout(progress_layout)
        content_layout.addWidget(progress_group)
        
        # 7. Preview Section
        preview_group = QGroupBox("Preview - Split PDFs")
        self._style_group_box(preview_group)
        preview_main_layout = QHBoxLayout()
        
        # Left: List of split PDFs
        split_list_container = QWidget()
        split_list_container_layout = QVBoxLayout(split_list_container)
        split_list_container_layout.setContentsMargins(0, 0, 0, 0)
        
        refresh_layout = QHBoxLayout()
        refresh_label = QLabel("Split PDFs:")
        refresh_label.setStyleSheet("font-weight: bold; color: #212529;")
        refresh_layout.addWidget(refresh_label)
        self.refresh_split_btn = QPushButton("Refresh")
        self.refresh_split_btn.setMaximumWidth(100)
        self.refresh_split_btn.clicked.connect(self._refresh_split_pdfs_list)
        refresh_layout.addWidget(self.refresh_split_btn)
        split_list_container_layout.addLayout(refresh_layout)
        
        self.split_pdfs_tree = QTreeWidget()
        self.split_pdfs_tree.setMinimumHeight(500)
        self.split_pdfs_tree.setHeaderLabel("Split PDF Files")
        self.split_pdfs_tree.setRootIsDecorated(True)  # Show expand/collapse arrows
        self.split_pdfs_tree.setAlternatingRowColors(True)  # Better visual separation
        
        # Set header properties directly
        header = self.split_pdfs_tree.header()
        header.setStyleSheet("""
            QHeaderView::section {
                background-color: #f8f9fa;
                color: black;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #dee2e6;
                padding: 4px;
            }
        """)
        self.split_pdfs_tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                font-size: 10pt;
                color: black;
                outline: none;
                show-decoration-selected: 0;
            }
            QTreeWidget::header {
                background-color: #f8f9fa;
                color: black;
                font-weight: bold;
                border-bottom: 1px solid #dee2e6;
                padding: 4px;
            }
            QTreeWidget::header::section {
                background-color: #f8f9fa;
                color: black;
                font-weight: bold;
                border: none;
            }
            QTreeWidget::item {
                padding: 4px;
                border-bottom: 1px solid #f8f9fa;
                color: black;
                outline: none;
                border: none;
            }
            QTreeWidget::item:selected {
                background-color: #e3f2fd;
                color: black;
                outline: none;
                border: none;
                show-decoration-selected: 0;
            }
            QTreeWidget::item:selected:focus {
                background-color: #e3f2fd;
                color: black;
                outline: none;
                border: none;
            }
            QTreeWidget::item:focus {
                outline: none;
                border: none;
                background-color: #e3f2fd;
            }
            QTreeWidget::item:hover {
                background-color: #f8f9fa;
                color: black;
                outline: none;
                border: none;
            }
            QTreeWidget::branch {
                background-color: transparent;
            }
        """)
        self.split_pdfs_tree.itemClicked.connect(self._on_split_pdf_selected)
        split_list_container_layout.addWidget(self.split_pdfs_tree)
        
        preview_main_layout.addWidget(split_list_container, 1)
        
        # Right: Preview of selected split PDF
        split_preview_container = QWidget()
        split_preview_container_layout = QVBoxLayout(split_preview_container)
        split_preview_container_layout.setContentsMargins(0, 0, 0, 0)
        
        self.split_preview_info_label = QLabel("Select a PDF to preview")
        self.split_preview_info_label.setStyleSheet("font-weight: bold; color: #28a745; padding: 10px; font-size: 11pt;")
        self.split_preview_info_label.setAlignment(Qt.AlignCenter)
        self.split_preview_info_label.setWordWrap(True)
        split_preview_container_layout.addWidget(self.split_preview_info_label)
        
        self.split_pdf_preview_scroll = QScrollArea()
        self.split_pdf_preview_scroll.setWidgetResizable(True)
        self.split_pdf_preview_scroll.setMinimumHeight(600)
        self.split_pdf_preview_label = QLabel("No preview available")
        self.split_pdf_preview_label.setAlignment(Qt.AlignCenter)
        self.split_pdf_preview_label.setStyleSheet("""
            border: 2px solid #dee2e6; 
            background-color: #f8f9fa; 
            padding: 20px;
            font-size: 10pt;
            color: #6c757d;
        """)
        self.split_pdf_preview_scroll.setWidget(self.split_pdf_preview_label)
        split_preview_container_layout.addWidget(self.split_pdf_preview_scroll)
        
        preview_main_layout.addWidget(split_preview_container, 3)
        
        preview_group.setLayout(preview_main_layout)
        content_layout.addWidget(preview_group)
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Initialize state
        self.split_pdf_path = ""
        self.split_subfolder = ""
        self.custom_ranges = []  # List of tuples (from_page, to_page)
        
        return container

    def _style_group_box(self, group_box):
        """Apply custom styling to group box titles"""
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

    def _ensure_google_sans(self):
        try:
            fonts_dir = Path('fonts')
            if fonts_dir.exists():
                for ttf in fonts_dir.glob('*.ttf'):
                    QFontDatabase.addApplicationFont(str(ttf))
            for fam in ("Google Sans", "Product Sans"):
                if fam in QFontDatabase().families():
                    self.setFont(QFont(fam))
                    break
        except Exception:
            pass

    # Navigation methods
    def _show_initial_buttons(self):
        """Show initial Merge/Split buttons"""
        self.current_mode = None
        self.initial_buttons_container.setVisible(True)
        self.merge_container.setVisible(False)
        self.split_container.setVisible(False)

    def _show_merge_ui(self):
        """Show merge UI"""
        self.current_mode = 'merge'
        self.initial_buttons_container.setVisible(False)
        self.merge_container.setVisible(True)
        self.split_container.setVisible(False)
        
        # Refresh merged PDFs list when showing merge UI
        self._refresh_merged_pdfs_list()

    def _show_split_ui(self):
        """Show split UI"""
        self.current_mode = 'split'
        self.initial_buttons_container.setVisible(False)
        self.merge_container.setVisible(False)
        self.split_container.setVisible(True)
        
        # Refresh split PDFs list when showing split UI
        self._refresh_split_pdfs_list()

    def _open_page_impose(self):
        """Open Page Impose section while keeping PDF Desk button highlighted"""
        # Find the main application window
        parent_window = self.window()
        if hasattr(parent_window, 'stacked_widget'):
            # Directly switch to page impose widget (index 7) without changing button highlighting
            parent_window.stacked_widget.setCurrentIndex(7)
            
            # Ensure PDF Desk button stays highlighted and all others are inactive
            buttons_to_check = [
                'pdf_split_btn', 'colour_conv_btn', 'pdf_to_images_btn', 
                'images_to_rip_btn', 'print_rip_btn', 'consolidated_btn', 
                'build_csv_btn', 'multi_server_btn'
            ]
            
            for btn_name in buttons_to_check:
                if hasattr(parent_window, btn_name):
                    btn = getattr(parent_window, btn_name)
                    # Keep PDF Desk button active, deactivate all others
                    is_active = (btn_name == 'pdf_split_btn')
                    btn.setProperty("active", is_active)
                    btn.style().unpolish(btn)
                    btn.style().polish(btn)

    # Merge functionality
    def _browse_merge_folder(self):
        """Browse for input folder containing PDFs"""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder with PDFs", self.folder_path or os.getcwd())
        if folder:
            self.folder_path = folder
            self.merge_folder_edit.setText(folder)
            self._load_pdfs_from_folder()

    def _load_pdfs_from_folder(self):
        """Load all PDFs from the selected folder (runs in background thread)"""
        if not self.folder_path:
            return
            
        try:
            # Clear existing data
            self.pdf_files_data.clear()
            self.pdf_list_widget.clear()
            
            # Show scanning progress
            self.merge_scan_progress_bar.setVisible(True)
            self.merge_scan_progress_bar.setValue(0)
            self.merge_status_label.setText("Scanning folder...")
            
            # Disable browse button during scan
            browse_btn = self.findChild(QPushButton, "browse_folder_btn")
            if browse_btn:
                browse_btn.setEnabled(False)
            
            # Create worker and thread
            self.scan_thread = QThread()
            self.scan_worker = PDFScanWorker(self.folder_path)
            self.scan_worker.moveToThread(self.scan_thread)
            
            # Connect signals
            self.scan_thread.started.connect(self.scan_worker.run)
            self.scan_worker.finished.connect(self.scan_thread.quit)
            self.scan_worker.finished.connect(self.scan_worker.deleteLater)
            self.scan_thread.finished.connect(self.scan_thread.deleteLater)
            self.scan_worker.progress.connect(self._on_pdf_scan_progress)
            self.scan_worker.completed.connect(self._on_pdf_scan_complete)
            self.scan_worker.error.connect(self._on_pdf_scan_error)
            
            # Start scanning
            self.scan_thread.start()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not start PDF scan: {e}")
            self.merge_scan_progress_bar.setVisible(False)

    def _update_pdf_list(self):
        """Update the PDF list widget"""
        self.pdf_list_widget.clear()
        
        # Get dimension data if available
        dimension_data = getattr(self, 'dimension_data', None)
        file_main_by_path = dimension_data.get("file_main_by_path", {}) if dimension_data else {}
        differing_paths = set(dimension_data.get("differing_paths", [])) if dimension_data else set()
        
        for idx, pdf_data in enumerate(self.pdf_files_data):
            # Create list item with number, name, pages, dimensions, and remove button
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(5, 2, 5, 2)
            
            # Number
            num_label = QLabel(f"{idx + 1}.")
            num_label.setMinimumWidth(30)
            num_label.setStyleSheet("font-weight: bold;")
            item_layout.addWidget(num_label)
            
            # Get dimension info for this PDF
            pdf_path = pdf_data['path']
            pdf_size = file_main_by_path.get(pdf_path, (0, 0))
            is_differing = pdf_path in differing_paths
            
            # Format dimension string
            if pdf_size != (0, 0):
                try:
                    from .pdf_page_dimension_checker import format_points_to_mm
                except Exception:
                    from pages.merge_split.pdf_page_dimension_checker import format_points_to_mm
                dim_str = format_points_to_mm(pdf_size)
            else:
                dim_str = "Unknown size"
            
            # PDF name, pages, and dimensions
            name_text = f"{pdf_data['name']} ({pdf_data['pages']} pages, {dim_str})"
            name_label = QLabel(name_text)
            
            # Color coding: red for differing sizes, gray for excluded, normal for included
            if is_differing:
                name_label.setStyleSheet("color: #dc3545; font-weight: bold;" if pdf_data['included'] else "color: #dc3545; text-decoration: line-through;")
            elif pdf_data['included']:
                name_label.setStyleSheet("color: #212529;")
            else:
                name_label.setStyleSheet("color: #6c757d; text-decoration: line-through;")
                
            item_layout.addWidget(name_label, 1)
            
            # Remove/Include button (red X or green checkmark)
            toggle_btn = QPushButton("✖" if pdf_data['included'] else "✓")
            toggle_btn.setMaximumWidth(40)
            toggle_btn.setStyleSheet(
                "background-color: #dc3545; color: white; font-weight: bold; border-radius: 4px;" if pdf_data['included']
                else "background-color: #28a745; color: white; font-weight: bold; border-radius: 4px;"
            )
            toggle_btn.clicked.connect(lambda checked, i=idx: self._toggle_pdf_inclusion(i))
            item_layout.addWidget(toggle_btn)
            
            # Create list item and store PDF data reference
            list_item = QListWidgetItem()
            list_item.setSizeHint(item_widget.sizeHint())
            list_item.setData(Qt.UserRole, idx)  # Store original index
            self.pdf_list_widget.addItem(list_item)
            self.pdf_list_widget.setItemWidget(list_item, item_widget)
        
        self._update_merge_button_state()

    def _toggle_pdf_inclusion(self, index):
        """Toggle whether a PDF is included in the merge"""
        if 0 <= index < len(self.pdf_files_data):
            self.pdf_files_data[index]['included'] = not self.pdf_files_data[index]['included']
            self._update_pdf_list()

    def _on_pdf_order_changed(self):
        """Handle when PDFs are reordered via drag-drop"""
        # Reconstruct pdf_files_data based on current list order
        new_order = []
        for i in range(self.pdf_list_widget.count()):
            item = self.pdf_list_widget.item(i)
            original_idx = item.data(Qt.UserRole)
            if original_idx is not None and original_idx < len(self.pdf_files_data):
                new_order.append(self.pdf_files_data[original_idx])
        
        if len(new_order) == len(self.pdf_files_data):
            self.pdf_files_data = new_order
            self._update_pdf_list()

    def _set_merge_mode(self, mode):
        """Set the merge mode"""
        self.merge_mode = mode

    def _on_blank_page_option_changed(self, index):
        """Handle blank page option change"""
        modes = ["none", "alternative", "end_of_final", "end_of_each"]
        self.blank_page_mode = modes[index]

    def _browse_output_folder(self):
        """Browse for output folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.output_folder)
        if folder:
            self.output_folder = folder
            self.merge_output_folder_edit.setText(folder)
    
    def _update_merge_button_state(self):
        """Enable/disable merge start button based on selections"""
        included_count = sum(1 for pdf in self.pdf_files_data if pdf['included'])
        has_name = bool(self.merge_output_name_edit.text().strip())
        self.merge_start_btn.setEnabled(included_count >= 1 and has_name)

    def _on_pdf_scan_progress(self, current, total):
        """Update scanning progress"""
        if total > 0:
            percent = int((current / total) * 100)
            self.merge_scan_progress_bar.setValue(percent)
        self.merge_status_label.setText(f"Scanning PDFs... {current}/{total}")

    def _on_pdf_scan_complete(self, pdf_files_data):
        """Handle completion of PDF scanning"""
        # Hide scanning progress
        self.merge_scan_progress_bar.setVisible(False)
        
        # Re-enable browse button
        browse_btn = self.findChild(QPushButton, "browse_folder_btn")
        if browse_btn:
            browse_btn.setEnabled(True)
        
        # Store and display results
        self.pdf_files_data = pdf_files_data
        self._update_pdf_list()
        
        # Update status
        self.merge_status_label.setText(f"Found {len(pdf_files_data)} PDF files")
        self._update_merge_button_state()
        
        # Start dimension checking after PDF scanning is complete
        self._start_dimension_check()

    def _on_pdf_scan_error(self, error_message):
        """Handle PDF scanning errors"""
        self.merge_scan_progress_bar.setVisible(False)
        
        # Re-enable browse button
        browse_btn = self.findChild(QPushButton, "browse_folder_btn")
        if browse_btn:
            browse_btn.setEnabled(True)
        
        self.merge_status_label.setText(f"Scan error: {error_message}")
        QMessageBox.warning(self, "Scan Error", f"Could not scan PDF files:\n{error_message}")

    def _start_dimension_check(self):
        """Start dimension checking in background thread"""
        if not self.folder_path:
            return
            
        try:
            # Show checking message
            self.merge_dim_label.setText("Checking page sizes…")
            self.merge_dim_label.setStyleSheet("color: #6c757d;")
            
            # Cancel/cleanup any previous dimension thread
            if hasattr(self, 'dim_thread') and self.dim_thread is not None:
                pass  # Let it finish naturally
            
            # Create and start dimension worker
            self.dim_thread = QThread()
            self.dim_worker = PDFDimensionCheckWorker(folder_path=self.folder_path)
            self.dim_worker.moveToThread(self.dim_thread)
            
            # Connect signals
            self.dim_thread.started.connect(self.dim_worker.run)
            self.dim_worker.finished.connect(self.dim_thread.quit)
            self.dim_worker.finished.connect(self.dim_worker.deleteLater)
            self.dim_thread.finished.connect(self.dim_thread.deleteLater)
            self.dim_worker.error.connect(self._on_dimension_error)
            self.dim_worker.success.connect(self._on_dimension_success)
            
            # Start checking
            self.dim_thread.start()
            
        except Exception as e:
            self.merge_dim_label.setText("Dimension check failed")
            self.merge_dim_label.setStyleSheet("color: #dc3545; font-weight: 500;")

    def _on_dimension_error(self, msg: str):
        """Handle dimension checking errors"""
        try:
            self.merge_dim_label.setText("Page size check failed")
            self.merge_dim_label.setStyleSheet("color: #dc3545; font-weight: 500;")
        except Exception:
            pass

    def _on_dimension_success(self, payload: dict):
        """Handle dimension checking success"""
        try:
            # If user navigated away or label missing, ignore
            if not hasattr(self, 'merge_dim_label') or self.merge_dim_label is None:
                return
                
            all_same = payload.get("all_same", False)
            ref_size = payload.get("ref_size", (0, 0))
            ref_mm = payload.get("ref_mm", "")
            differing = payload.get("differing", [])
            file_main = payload.get("file_main", {})

            if all_same and ref_size != (0, 0):
                self.merge_dim_label.setText(f"All PDFs/pages share the same size: {ref_mm}")
                self.merge_dim_label.setStyleSheet("color: #198754; font-weight: 500;")
            else:
                if not differing:
                    self.merge_dim_label.setText("Could not determine consistent page sizes.")
                    self.merge_dim_label.setStyleSheet("color: #dc3545; font-weight: 500;")
                else:
                    # Show up to first 6 differing files, then summarize
                    max_show = 6
                    shown = differing[:max_show]
                    rest = len(differing) - len(shown)
                    parts = []
                    for fname in shown:
                        parts.append(f"{fname}")
                    more = f" and {rest} more" if rest > 0 else ""
                    self.merge_dim_label.setText("Different sizes detected: " + ", ".join(parts) + more)
                    self.merge_dim_label.setStyleSheet("color: #fd7e14; font-weight: 500;")

            # Store dimension data for later use in PDF list display
            self.dimension_data = payload
            
            # Update PDF list to show dimensions
            self._update_pdf_list()
            
        except Exception as e:
            self.merge_dim_label.setText(f"Dimension display error: {str(e)}")
            self.merge_dim_label.setStyleSheet("color: #dc3545; font-weight: 500;")

    def _start_merge_process(self):
        """Start the merge process in a background thread"""
        # Get included PDFs in current order
        included_pdfs = [pdf for pdf in self.pdf_files_data if pdf['included']]
        
        if not included_pdfs:
            QMessageBox.warning(self, "No PDFs", "Please select at least one PDF to merge")
            return
        
        output_name = self.merge_output_name_edit.text().strip()
        if not output_name:
            QMessageBox.warning(self, "No Name", "Please enter an output filename")
            return
        
        # Disable controls
        self.merge_start_btn.setEnabled(False)
        self.merge_stop_btn.setEnabled(True)  # ADD THIS
        self.merge_progress_bar.setVisible(True)
        self.merge_progress_bar.setMaximum(100)
        self.merge_progress_bar.setValue(0)
        self.merge_status_label.setText("Starting merge...")
        
        # Start worker thread
        self.merge_thread = QThread()
        self.merge_worker = PDFMergeWorker(
            pdf_files=included_pdfs,
            output_folder=self.output_folder,
            output_name=output_name,
            merge_mode=self.merge_mode,
            blank_page_mode=self.blank_page_mode
        )
        self.merge_worker.moveToThread(self.merge_thread)
        
        self.merge_thread.started.connect(self.merge_worker.run)
        self.merge_worker.finished.connect(self.merge_thread.quit)
        self.merge_worker.finished.connect(self.merge_worker.deleteLater)
        self.merge_thread.finished.connect(self.merge_thread.deleteLater)
        self.merge_worker.progress.connect(self._on_merge_progress)
        self.merge_worker.error.connect(self._on_merge_error)
        self.merge_worker.success.connect(self._on_merge_success)
        
        self.merge_thread.start()

    def _stop_merge_process(self):
        """Stop the merge process"""
        if hasattr(self, 'merge_worker') and self.merge_worker:
            self.merge_worker.cancel()
            self.merge_status_label.setText("Stopping merge...")
            self.merge_stop_btn.setEnabled(False)

    def _on_merge_progress(self, value, message):
        """Update merge progress (throttled)"""
        # Only update if value changed significantly or message changed
        if not hasattr(self, '_last_progress_value'):
            self._last_progress_value = -1
            self._last_progress_message = ""
        
        # Update only if progress changed by 1% or more, or message is different
        if abs(value - self._last_progress_value) >= 1 or message != self._last_progress_message:
            self.merge_progress_bar.setValue(value)
            self.merge_status_label.setText(message)
            self._last_progress_value = value
            self._last_progress_message = message

    def _on_merge_error(self, message):
        """Handle merge error"""
        self.merge_progress_bar.setVisible(False)
        self.merge_start_btn.setEnabled(True)
        self.merge_stop_btn.setEnabled(False)  # ADD THIS
        QMessageBox.critical(self, "Merge Error", message)
        self.merge_status_label.setText(f"Error: {message}")

    def _on_merge_success(self, output_path):
        """Handle merge success"""
        self.merge_progress_bar.setVisible(False)
        self.merge_start_btn.setEnabled(True)
        self.merge_stop_btn.setEnabled(False)
        
        # Refresh the merged PDFs list
        self._refresh_merged_pdfs_list()
        
        QMessageBox.information(self, "Merge Complete", 
                              f"Successfully merged PDFs into:\n{os.path.basename(output_path)}")
        self.merge_status_label.setText(f"Merge completed: {os.path.basename(output_path)}")

    def _refresh_merged_pdfs_list(self):
        """Refresh the list of merged PDFs from output folder"""
        self.merged_pdfs_list.clear()
        self.merged_pdf_preview_label.clear()
        self.preview_pdf_info_label.setText("Select a PDF to preview")
        
        if not os.path.exists(self.output_folder):
            self.preview_pdf_info_label.setText("Output folder not found")
            return
        
        try:
            # Get all PDF files from output folder
            pdf_files = [f for f in os.listdir(self.output_folder) 
                         if f.lower().endswith('.pdf') and not f.startswith('_temp')]
            
            if not pdf_files:
                self.preview_pdf_info_label.setText("No merged PDFs found in output folder")
                return
            
            # Sort by modification time (newest first)
            pdf_files_with_time = []
            for pdf_file in pdf_files:
                pdf_path = os.path.join(self.output_folder, pdf_file)
                try:
                    mtime = os.path.getmtime(pdf_path)
                    pdf_files_with_time.append((pdf_file, pdf_path, mtime))
                except:
                    continue
            
            pdf_files_with_time.sort(key=lambda x: x[2], reverse=True)
            
            # Add to list widget
            for pdf_file, pdf_path, _ in pdf_files_with_time:
                item = QListWidgetItem(pdf_file)
                item.setData(Qt.UserRole, pdf_path)  # Store full path
                self.merged_pdfs_list.addItem(item)
            
            self.preview_pdf_info_label.setText(f"Found {len(pdf_files_with_time)} merged PDF(s)")
            
        except Exception as e:
            self.preview_pdf_info_label.setText(f"Error: {str(e)}")

    def _on_merged_pdf_selected(self, item):
        """Handle when a merged PDF is selected from the list"""
        pdf_path = item.data(Qt.UserRole)
        
        if not pdf_path or not os.path.exists(pdf_path):
            self.preview_pdf_info_label.setText("PDF file not found")
            self.merged_pdf_preview_label.setText("File not found")
            return
        
        try:
            # Open PDF and get info
            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            
            # Update info label with more details
            pdf_name = os.path.basename(pdf_path)
            file_size = os.path.getsize(pdf_path) / (1024 * 1024)  # MB
            self.preview_pdf_info_label.setText(
                f"📄 {pdf_name}\n{num_pages} pages | {file_size:.2f} MB"
            )
            
            # Render first page as preview
            if num_pages > 0:
                page = doc[0]
                # Render at 200 DPI for better quality in larger preview
                mat = fitz.Matrix(200/72.0, 200/72.0)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to QImage
                if pix.alpha:
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888)
                else:
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                qimg = qimg.copy()
                
                # Create pixmap and scale to fit
                pixmap = QPixmap.fromImage(qimg)
                max_w = self.merged_pdf_preview_scroll.width() - 50
                max_h = self.merged_pdf_preview_scroll.height() - 50
                if max_w > 0 and max_h > 0:
                    pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                self.merged_pdf_preview_label.setPixmap(pixmap)
            else:
                self.merged_pdf_preview_label.setText("PDF has no pages")
            
            doc.close()
            
        except Exception as e:
            self.preview_pdf_info_label.setText(f"Preview error: {str(e)}")
            self.merged_pdf_preview_label.setText(f"Could not load preview:\n{str(e)}")

    # Split functionality handlers
    def _browse_split_pdf(self):
        """Browse for input PDF file to split"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select PDF to Split", 
            os.getcwd(), 
            "PDF Files (*.pdf)"
        )
        if file_path:
            self.split_pdf_path = file_path
            self.split_pdf_edit.setText(file_path)
            self._load_split_pdf_info()

    def _load_split_pdf_info(self):
        """Load and display basic info, then defer heavy work to background thread"""
        if not self.split_pdf_path or not os.path.exists(self.split_pdf_path):
            self.split_pdf_info_label.setText("PDF file not found")
            self.split_start_btn.setEnabled(False)
            return
        
        try:
            # Show immediate status without opening the PDF in UI thread
            file_size = os.path.getsize(self.split_pdf_path) / (1024 * 1024)  # MB
            self.split_pdf_info_label.setText(
                f"File size: {file_size:.2f} MB | Checking dimensions, please wait..."
            )
            self.split_pdf_info_label.setStyleSheet("color: #0d6efd; font-weight: 500; padding: 5px;")
            
            # Disable start until we confirm page count
            has_name = bool(self.split_output_name_edit.text().strip())
            self.split_start_btn.setEnabled(False if not has_name else False)
            
            # Kick off dimension checking in background
            self._check_pdf_dimensions()
            
        except Exception as e:
            self.split_pdf_info_label.setText(f"Error reading PDF: {str(e)}")
            self.split_pdf_info_label.setStyleSheet("color: #dc3545; font-weight: bold; padding: 5px;")
            self.split_start_btn.setEnabled(False)

    def _browse_split_output_folder(self):
        """Browse for output folder"""
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select Output Folder", 
            self.split_output_folder_edit.text()
        )
        if folder:
            self.split_output_folder_edit.setText(folder)

    def _update_split_button_state(self):
        """Enable/disable split start button based on selections"""
        has_pdf = bool(self.split_pdf_path and os.path.exists(self.split_pdf_path))
        has_name = bool(self.split_output_name_edit.text().strip())
        self.split_start_btn.setEnabled(has_pdf and has_name)

    def _start_split_process(self):
        """Start the PDF split process"""
        if not self.split_pdf_path or not os.path.exists(self.split_pdf_path):
            QMessageBox.warning(self, "No PDF", "Please select a valid PDF file to split")
            return
        
        output_name = self.split_output_name_edit.text().strip()
        if not output_name:
            QMessageBox.warning(self, "No Name", "Please enter a base name for split PDFs")
            return
        
        # Determine split mode
        if self.range_split_radio.isChecked():
            split_mode = "range"
            pages_per_split = self.pages_per_split_spin.value()
            custom_ranges = None
        elif self.custom_ranges_radio.isChecked():
            split_mode = "custom"
            pages_per_split = None
            custom_ranges = self.custom_ranges.copy()
            
            # Validate we have ranges
            if not custom_ranges:
                QMessageBox.warning(self, "No Ranges", "Please add at least one custom range")
                return
        else:
            split_mode = "odd_even"
            pages_per_split = None
            custom_ranges = None
        
        # Get options
        add_blank = self.split_add_blank_checkbox.isChecked()
        reverse_split = self.split_reverse_checkbox.isChecked()
        output_folder = self.split_output_folder_edit.text()
        
        # Create subfolder name based on PDF name
        pdf_basename = os.path.splitext(os.path.basename(self.split_pdf_path))[0]
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.split_subfolder = f"{pdf_basename}_split_{timestamp}"
        split_output_path = os.path.join(output_folder, self.split_subfolder)
        
        # Disable controls
        self.split_start_btn.setEnabled(False)
        self.split_stop_btn.setEnabled(True)
        self.split_progress_bar.setVisible(True)
        self.split_progress_bar.setValue(0)
        self.split_status_label.setText("Starting split...")
        
        # Start worker thread
        self.split_thread = QThread()
        self.split_worker = PDFSplitWorker(
            pdf_path=self.split_pdf_path,
            output_folder=split_output_path,
            base_name=output_name,
            split_mode=split_mode,
            pages_per_split=pages_per_split,
            add_blank=add_blank,
            reverse_split=reverse_split,
            custom_ranges=custom_ranges  # ADD THIS
        )
        self.split_worker.moveToThread(self.split_thread)
        
        self.split_thread.started.connect(self.split_worker.run)
        self.split_worker.finished.connect(self.split_thread.quit)
        self.split_worker.finished.connect(self.split_worker.deleteLater)
        self.split_thread.finished.connect(self.split_thread.deleteLater)
        self.split_worker.progress.connect(self._on_split_progress)
        self.split_worker.error.connect(self._on_split_error)
        self.split_worker.success.connect(self._on_split_success)
        
        self.split_thread.start()

    def _stop_split_process(self):
        """Stop the split process"""
        reply = QMessageBox.question(
            self, 
            'Stop Split',
            'Are you sure you want to stop the split process?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if hasattr(self, 'split_worker') and self.split_worker:
                self.split_worker.cancel()
                self.split_status_label.setText("Stopping split...")
                self.split_stop_btn.setEnabled(False)

    def _on_split_progress(self, value, message):
        """Update split progress"""
        self.split_progress_bar.setValue(value)
        self.split_status_label.setText(message)

    def _on_split_error(self, message):
        """Handle split error"""
        self.split_progress_bar.setVisible(False)
        self.split_start_btn.setEnabled(True)
        self.split_stop_btn.setEnabled(False)
        QMessageBox.critical(self, "Split Error", message)
        self.split_status_label.setText(f"Error: {message}")

    def _on_split_success(self, output_folder, num_files):
        """Handle split success"""
        self.split_progress_bar.setVisible(False)
        self.split_start_btn.setEnabled(True)
        self.split_stop_btn.setEnabled(False)
        
        # Refresh split PDFs list
        self._refresh_split_pdfs_list()
        
        QMessageBox.information(
            self, 
            "Split Complete", 
            f"Successfully split PDF into {num_files} files!\nSaved to: {os.path.basename(output_folder)}"
        )
        self.split_status_label.setText(f"Split completed: {num_files} files created")

    def _refresh_split_pdfs_list(self):
        """Refresh the tree of split PDFs organized by subfolders"""
        self.split_pdfs_tree.clear()
        self.split_pdf_preview_label.clear()
        self.split_preview_info_label.setText("Select a PDF to preview")
        
        output_folder = self.split_output_folder_edit.text()
        if not os.path.exists(output_folder):
            self.split_preview_info_label.setText("Output folder not found")
            return
        
        try:
            # Organize PDFs by subfolder
            subfolder_data = {}
            
            # Walk through all subdirectories
            for root, dirs, files in os.walk(output_folder):
                # Skip the root output folder itself
                if root == output_folder:
                    continue
                
                # Get relative path from output folder
                rel_path = os.path.relpath(root, output_folder)
                subfolder_name = os.path.basename(rel_path)
                
                # Collect PDF files in this subfolder
                pdf_files = []
                for file in files:
                    if file.lower().endswith('.pdf') and not file.startswith('_temp'):
                        pdf_path = os.path.join(root, file)
                        mtime = os.path.getmtime(pdf_path)
                        pdf_files.append((file, pdf_path, mtime))
                
                if pdf_files:
                    # Sort PDFs by modification time (newest first)
                    pdf_files.sort(key=lambda x: x[2], reverse=True)
                    subfolder_data[subfolder_name] = {
                        'path': root,
                        'files': pdf_files,
                        'mtime': max(f[2] for f in pdf_files)  # Use latest file time for subfolder
                    }
            
            if not subfolder_data:
                self.split_preview_info_label.setText("No split PDFs found")
                return
            
            # Sort subfolders by modification time (newest first)
            sorted_subfolders = sorted(subfolder_data.items(), key=lambda x: x[1]['mtime'], reverse=True)
            
            total_files = 0
            
            # Create tree structure
            for subfolder_name, subfolder_info in sorted_subfolders:
                # Create subfolder parent item
                subfolder_item = QTreeWidgetItem(self.split_pdfs_tree)
                subfolder_item.setText(0, f"📁 {subfolder_name}")
                subfolder_item.setData(0, Qt.UserRole, subfolder_info['path'])  # Store folder path
                subfolder_item.setData(1, Qt.UserRole, 'folder')  # Mark as folder
                
                # Add PDF files as children
                for pdf_file, pdf_path, mtime in subfolder_info['files']:
                    file_item = QTreeWidgetItem(subfolder_item)
                    file_item.setText(0, f"📄 {pdf_file}")
                    file_item.setData(0, Qt.UserRole, pdf_path)  # Store file path
                    file_item.setData(1, Qt.UserRole, 'file')  # Mark as file
                    total_files += 1
                
                # Expand subfolder by default to show files
                subfolder_item.setExpanded(True)
            
            self.split_preview_info_label.setText(f"Found {len(subfolder_data)} subfolder(s) with {total_files} PDF(s)")
            
        except Exception as e:
            self.split_preview_info_label.setText(f"Error: {str(e)}")

    def _on_split_pdf_selected(self, item, column):
        """Handle when a split PDF or folder is selected in the tree"""
        item_type = item.data(1, Qt.UserRole)
        item_path = item.data(0, Qt.UserRole)
        
        # Only show preview for files, not folders
        if item_type != 'file':
            self.split_preview_info_label.setText("Select a PDF file to preview")
            self.split_pdf_preview_label.setText("No preview available - select a PDF file")
            self.split_pdf_preview_label.setStyleSheet("""
                border: 2px solid #dee2e6; 
                background-color: #f8f9fa; 
                padding: 20px;
                font-size: 10pt;
                color: #6c757d;
            """)
            return
        
        pdf_path = item_path
        
        if not pdf_path or not os.path.exists(pdf_path):
            self.split_preview_info_label.setText("PDF file not found")
            self.split_pdf_preview_label.setText("File not found")
            return
        
        try:
            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            
            pdf_name = os.path.basename(pdf_path)
            file_size = os.path.getsize(pdf_path) / (1024 * 1024)
            self.split_preview_info_label.setText(
                f"📄 {pdf_name}\n{num_pages} pages | {file_size:.2f} MB"
            )
            
            if num_pages > 0:
                page = doc[0]
                mat = fitz.Matrix(200/72.0, 200/72.0)
                pix = page.get_pixmap(matrix=mat)
                
                if pix.alpha:
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888)
                else:
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                qimg = qimg.copy()
                
                pixmap = QPixmap.fromImage(qimg)
                max_w = self.split_pdf_preview_scroll.width() - 50
                max_h = self.split_pdf_preview_scroll.height() - 50
                if max_w > 0 and max_h > 0:
                    pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                self.split_pdf_preview_label.setPixmap(pixmap)
            else:
                self.split_pdf_preview_label.setText("PDF has no pages")
            
            doc.close()
            
        except Exception as e:
            self.split_preview_info_label.setText(f"Preview error: {str(e)}")
            self.split_pdf_preview_label.setText(f"Could not load preview:\n{str(e)}")

    def _add_custom_range(self):
        """Add a custom range to the list"""
        from_page = self.custom_range_from_spin.value()
        to_page = self.custom_range_to_spin.value()
        
        # Validate range
        if from_page > to_page:
            QMessageBox.warning(self, "Invalid Range", "Start page must be less than or equal to end page")
            return
        
        # Check if we have a PDF loaded to validate against
        if self.split_pdf_path and os.path.exists(self.split_pdf_path):
            try:
                doc = fitz.open(self.split_pdf_path)
                total_pages = len(doc)
                doc.close()
                
                if from_page > total_pages or to_page > total_pages:
                    QMessageBox.warning(
                        self, 
                        "Invalid Range", 
                        f"Page range exceeds PDF page count ({total_pages} pages)"
                    )
                    return
            except:
                pass
        
        # Check for overlapping ranges
        for existing_from, existing_to in self.custom_ranges:
            if not (to_page < existing_from or from_page > existing_to):
                QMessageBox.warning(
                    self, 
                    "Overlapping Range", 
                    f"Range {from_page}-{to_page} overlaps with existing range {existing_from}-{existing_to}"
                )
                return
        
        # Add range
        self.custom_ranges.append((from_page, to_page))
        self.custom_ranges.sort()  # Keep sorted by start page
        
        # Update list display
        self._update_custom_ranges_list()
        
        # Auto-increment for next range
        self.custom_range_from_spin.setValue(to_page + 1)
        self.custom_range_to_spin.setValue(to_page + 1)

    def _remove_custom_range(self):
        """Remove selected custom range"""
        current_item = self.custom_ranges_list.currentRow()
        if current_item >= 0 and current_item < len(self.custom_ranges):
            self.custom_ranges.pop(current_item)
            self._update_custom_ranges_list()

    def _clear_custom_ranges(self):
        """Clear all custom ranges"""
        self.custom_ranges.clear()
        self._update_custom_ranges_list()

    def _update_custom_ranges_list(self):
        """Update the display of custom ranges"""
        self.custom_ranges_list.clear()
        for from_page, to_page in self.custom_ranges:
            range_text = f"Pages {from_page}-{to_page}"
            self.custom_ranges_list.addItem(range_text)

    def _check_pdf_dimensions(self):
        """Check dimensions of the selected PDF file"""
        if not self.split_pdf_path or not os.path.exists(self.split_pdf_path):
            return
        
        # Show progress in status
        self.split_status_label.setText("Checking PDF dimensions...")
        self.split_status_label.setStyleSheet("color: #007bff; font-style: italic;")
        
        # Create worker and thread
        self.dimension_thread = QThread()
        self.dimension_worker = SinglePDFDimensionCheckWorker(self.split_pdf_path)
        self.dimension_worker.moveToThread(self.dimension_thread)
        
        # Connect signals
        self.dimension_thread.started.connect(self.dimension_worker.run)
        self.dimension_worker.finished.connect(self.dimension_thread.quit)
        self.dimension_worker.finished.connect(self.dimension_worker.deleteLater)
        self.dimension_thread.finished.connect(self.dimension_thread.deleteLater)
        self.dimension_worker.progress.connect(self._on_dimension_check_progress)
        self.dimension_worker.result.connect(self._on_dimension_check_result)
        self.dimension_worker.error.connect(self._on_dimension_check_error)
        
        # Start checking
        self.dimension_thread.start()

    def _on_dimension_check_progress(self, percent, message):
        """Update dimension check progress"""
        self.split_status_label.setText(f"Checking dimensions... {message}")

    def _on_dimension_check_result(self, result):
        """Handle dimension check result"""
        # Reset status
        self.split_status_label.setText("Ready to split")
        self.split_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        
        # Update info label with discovered page count
        try:
            pdf_name = os.path.basename(self.split_pdf_path)
            if result and 'total_pages' in result:
                # Keep prior size text if present, append page count
                text = self.split_pdf_info_label.text()
                page_info = f"Total pages: {result['total_pages']}"
                if 'File size' in text:
                    self.split_pdf_info_label.setText(text.replace('Checking dimensions, please wait...', page_info))
                else:
                    self.split_pdf_info_label.setText(page_info)
                self.split_pdf_info_label.setStyleSheet("color: #28a745; font-weight: bold; padding: 5px;")
        except Exception:
            pass
        
        # Enable start button now that we have info
        has_name = bool(self.split_output_name_edit.text().strip())
        self.split_start_btn.setEnabled(has_name and not result.get('error'))
        
        # Show result in popup
        pdf_name = os.path.basename(self.split_pdf_path)
        
        if result['error']:
            QMessageBox.critical(self, "Dimension Check Error", 
                               f"Error checking dimensions of {pdf_name}:\n{result['error']}")
        elif result['all_same']:
            dim = list(result['unique_dimensions'])[0]
            from .pdf_dimension_checker import format_dimensions
            
            QMessageBox.information(self, "Dimension Check Result", 
                                  f"✓ {pdf_name}\n\nAll {result['total_pages']} pages have the same dimensions:\n{format_dimensions(dim)}")
        else:
            # Show detailed info about different dimensions
            unique_count = len(result['unique_dimensions'])
            message = f"✗ {pdf_name}\n\nThis PDF has {unique_count} different page sizes:\n\n"
            
            for i, dim in enumerate(result['unique_dimensions'], 1):
                from .pdf_dimension_checker import format_dimensions
                message += f"{i}. {format_dimensions(dim)}\n"
            
            message += f"\nTotal pages: {result['total_pages']}"
            
            QMessageBox.warning(self, "Dimension Check Result", message)

    def _on_dimension_check_error(self, error_message):
        """Handle dimension check error"""
        # Reset status
        self.split_status_label.setText("Ready to split")
        self.split_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        
        # Show error
        pdf_name = os.path.basename(self.split_pdf_path) if self.split_pdf_path else "PDF"
        QMessageBox.critical(self, "Dimension Check Error", 
                           f"Error checking dimensions of {pdf_name}:\n{error_message}")


class PDFMergeWorker(QObject):
    """Worker for merging PDFs in background thread with various options"""
    finished = Signal()
    error = Signal(str)
    progress = Signal(int, str)  # percentage, message
    success = Signal(str)  # output file path

    def __init__(self, pdf_files, output_folder, output_name, merge_mode, blank_page_mode):
        super().__init__()
        self.pdf_files = pdf_files
        self.output_folder = output_folder
        self.output_name = output_name
        self.merge_mode = merge_mode
        self.blank_page_mode = blank_page_mode
        self._cancelled = False  # ADD THIS

    def _get_target_page_dimensions(self):
        """Get accurate target page dimensions (pt) using median across PDFs (floats)."""
        import statistics
        try:
            if not self.pdf_files:
                return 595.0, 842.0  # Default A4 in points

            widths = []
            heights = []
            for pdf in self.pdf_files:
                path = pdf.get('path')
                if not path:
                    continue
                try:
                    doc = fitz.open(path)
                    if len(doc) > 0:
                        rect = doc[0].rect
                        widths.append(float(rect.width))
                        heights.append(float(rect.height))
                    doc.close()
                except Exception:
                    continue

            if widths and heights:
                return float(statistics.median(widths)), float(statistics.median(heights))
            return 595.0, 842.0
        except Exception:
            return 595.0, 842.0

    def cancel(self):
        """Cancel the merge operation"""
        self._cancelled = True

    def run(self):
        import gc
        from PySide6.QtCore import QThread
        
        try:
            # Check cancellation at start
            if self._cancelled:
                self.progress.emit(0, "Merge cancelled")
                self.finished.emit()
                return
            
            # Create blank page document with dynamic dimensions
            target_width, target_height = self._get_target_page_dimensions()
            blank_doc = fitz.open()
            blank_page = blank_doc.new_page(width=target_width, height=target_height)
            blank_path = os.path.join(self.output_folder, "_temp_blank.pdf")
            blank_doc.save(blank_path)
            blank_doc.close()
            del blank_doc
            gc.collect()
            
            merged_doc = fitz.open()
            total_pdfs = len(self.pdf_files)
            
            for idx, pdf_data in enumerate(self.pdf_files):
                # CHECK CANCELLATION
                if self._cancelled:
                    merged_doc.close()
                    try:
                        os.remove(blank_path)
                    except:
                        pass
                    self.progress.emit(0, "Merge cancelled by user")
                    self.finished.emit()
                    return
                
                base_progress = int((idx / total_pdfs) * 90)
                self.progress.emit(base_progress, f"Merging {pdf_data['name']}...")
                
                QThread.msleep(1)
                
                source_doc = fitz.open(pdf_data['path'])
                num_pages = len(source_doc)
                
                if self.merge_mode == "individual_reverse":
                    reversed_pages = list(range(num_pages - 1, -1, -1))
                    source_doc.select(reversed_pages)
                
                # Adaptive chunk size based on PDF size
                if num_pages > 5000:
                    chunk_size = 50
                elif num_pages > 1000:
                    chunk_size = 100
                else:
                    chunk_size = 200
                
                for chunk_start in range(0, num_pages, chunk_size):
                    # CHECK CANCELLATION IN INNER LOOP
                    if self._cancelled:
                        source_doc.close()
                        merged_doc.close()
                        try:
                            os.remove(blank_path)
                        except:
                            pass
                        self.progress.emit(0, "Merge cancelled by user")
                        self.finished.emit()
                        return
                    
                    chunk_end = min(chunk_start + chunk_size, num_pages)
                    
                    chunk_progress = base_progress + int((chunk_start / num_pages) * (90 / total_pdfs))
                    self.progress.emit(
                        chunk_progress, 
                        f"Merging {pdf_data['name']} - page {chunk_start+1}/{num_pages}"
                    )
                    
                    merged_doc.insert_pdf(source_doc, from_page=chunk_start, to_page=chunk_end-1)
                    QThread.msleep(1)
                    
                    if chunk_start % 1000 == 0:
                        gc.collect()
                
                source_doc.close()
                del source_doc
                gc.collect()
                
                QThread.msleep(1)
            
            # CHECK CANCELLATION BEFORE POST-PROCESSING
            if self._cancelled:
                merged_doc.close()
                try:
                    os.remove(blank_path)
                except:
                    pass
                self.progress.emit(0, "Merge cancelled by user")
                self.finished.emit()
                return
            
            self.progress.emit(90, "Post-processing merged document...")
            QThread.msleep(1)
            
            # STEP 1: Handle merge mode transformations (reverse/individual_reverse already done during merge)
            if self.merge_mode == "reverse":
                if self._cancelled:
                    merged_doc.close()
                    try:
                        os.remove(blank_path)
                    except:
                        pass
                    self.progress.emit(0, "Merge cancelled by user")
                    self.finished.emit()
                    return
                
                self.progress.emit(92, "Reversing page order...")
                total_pages = len(merged_doc)
                reversed_pages = list(range(total_pages - 1, -1, -1))
                merged_doc.select(reversed_pages)
                gc.collect()
                QThread.msleep(1)
            
            # STEP 2: Handle "end_of_each" blank page insertion (WORKS FOR ALL MERGE MODES)
            if self.blank_page_mode == "end_of_each":
                if self._cancelled:
                    merged_doc.close()
                    try:
                        os.remove(blank_path)
                    except:
                        pass
                    self.progress.emit(0, "Merge cancelled by user")
                    self.finished.emit()
                    return
                
                self.progress.emit(93, "Adding blank pages at end of each PDF...")
                target_width, target_height = self._get_target_page_dimensions()
                
                if self.merge_mode == "reverse":
                    # For reverse merge: PDFs are in opposite order in the document
                    # Traverse pdf_files in reverse to match merged doc order
                    cumulative_position = 0
                    for pdf_idx in range(len(self.pdf_files) - 1, -1, -1):
                        cumulative_position += self.pdf_files[pdf_idx]['pages']
                        merged_doc.new_page(pno=cumulative_position, width=target_width, height=target_height)
                        cumulative_position += 1
                else:
                    # For forward or individual_reverse: PDFs are in normal order
                    cumulative_position = 0
                    for pdf_idx in range(len(self.pdf_files)):
                        cumulative_position += self.pdf_files[pdf_idx]['pages']
                        merged_doc.new_page(pno=cumulative_position, width=target_width, height=target_height)
                        cumulative_position += 1
                
                gc.collect()
                QThread.msleep(1)
            
            # STEP 3: Handle "alternative" blank page insertion
            if self.blank_page_mode == "alternative":
                if self._cancelled:
                    merged_doc.close()
                    try:
                        os.remove(blank_path)
                    except:
                        pass
                    self.progress.emit(0, "Merge cancelled by user")
                    self.finished.emit()
                    return
                
                self.progress.emit(94, "Adding alternative blank pages...")
                total_pages = len(merged_doc)
                
                if total_pages > 5000:
                    self.error.emit(f"Cannot add alternative blank pages: too many pages ({total_pages}).")
                    return
                
                temp_merged_path = os.path.join(self.output_folder, "_temp_merged.pdf")
                merged_doc.save(temp_merged_path)
                merged_doc.close()
                del merged_doc
                gc.collect()
                
                alt_doc = fitz.open()
                temp_merged = fitz.open(temp_merged_path)
                blank_temp = fitz.open(blank_path)
                
                batch_size = 20
                for batch_start in range(0, total_pages, batch_size):
                    if self._cancelled:
                        alt_doc.close()
                        temp_merged.close()
                        blank_temp.close()
                        try:
                            os.remove(blank_path)
                            os.remove(temp_merged_path)
                        except:
                            pass
                        self.progress.emit(0, "Merge cancelled by user")
                        self.finished.emit()
                        return
                    
                    batch_end = min(batch_start + batch_size, total_pages)
                    
                    alt_progress = 94 + int((batch_start / total_pages) * 4)
                    self.progress.emit(alt_progress, f"Adding blank pages {batch_start+1}/{total_pages}...")
                    
                    for page_num in range(batch_start, batch_end):
                        alt_doc.insert_pdf(temp_merged, from_page=page_num, to_page=page_num)
                        alt_doc.insert_pdf(blank_temp)
                    
                    QThread.msleep(1)
                    gc.collect()
                
                blank_temp.close()
                temp_merged.close()
                del blank_temp, temp_merged
                merged_doc = alt_doc
                gc.collect()
                
                try:
                    os.remove(temp_merged_path)
                except:
                    pass
            
            # STEP 4: Handle "end_of_final" blank page insertion
            if self.blank_page_mode == "end_of_final":
                if self._cancelled:
                    merged_doc.close()
                    try:
                        os.remove(blank_path)
                    except:
                        pass
                    self.progress.emit(0, "Merge cancelled by user")
                    self.finished.emit()
                    return
                
                self.progress.emit(98, "Adding final blank page...")
                blank_temp = fitz.open(blank_path)
                merged_doc.insert_pdf(blank_temp)
                blank_temp.close()
                del blank_temp
            
            # FINAL CANCELLATION CHECK BEFORE SAVING
            if self._cancelled:
                merged_doc.close()
                try:
                    os.remove(blank_path)
                except:
                    pass
                self.progress.emit(0, "Merge cancelled by user")
                self.finished.emit()
                return
            
            self.progress.emit(99, "Saving merged PDF...")
            output_filename = f"{self.output_name}.pdf" if not self.output_name.endswith('.pdf') else self.output_name
            output_path = os.path.join(self.output_folder, output_filename)
            
            counter = 1
            base_name = output_filename.replace('.pdf', '')
            while os.path.exists(output_path):
                output_filename = f"{base_name}_{counter}.pdf"
                output_path = os.path.join(self.output_folder, output_filename)
                counter += 1
            
            merged_doc.save(output_path)
            merged_doc.close()
            del merged_doc
            gc.collect()
            
            try:
                os.remove(blank_path)
            except:
                pass
            
            self.progress.emit(100, "Merge complete!")
            self.success.emit(output_path)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            gc.collect()
            self.finished.emit()


class PDFSplitWorker(QObject):
    """Worker for splitting PDFs in background thread"""
    finished = Signal()
    error = Signal(str)
    progress = Signal(int, str)
    success = Signal(str, int)  # output_folder, num_files

    def __init__(self, pdf_path, output_folder, base_name, split_mode, pages_per_split, add_blank, reverse_split, custom_ranges=None):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_folder = output_folder
        self.base_name = base_name
        self.split_mode = split_mode
        self.pages_per_split = pages_per_split
        self.add_blank = add_blank
        self.reverse_split = reverse_split
        self.custom_ranges = custom_ranges  # ADD THIS
        self._cancelled = False

    def _get_target_page_dimensions(self):
        """Get accurate target page dimensions (pt) from the split PDF (floats)."""
        try:
            doc = fitz.open(self.pdf_path)
            if len(doc) > 0:
                rect = doc[0].rect
                width = float(rect.width)
                height = float(rect.height)
                doc.close()
                return width, height
            else:
                doc.close()
                return 595.0, 842.0  # Default A4 if no pages
        except Exception:
            return 595.0, 842.0  # Default A4 if error

    def cancel(self):
        """Cancel the split operation"""
        self._cancelled = True

    def run(self):
        import gc
        from PySide6.QtCore import QThread
        
        try:
            if self._cancelled:
                self.progress.emit(0, "Split cancelled")
                self.finished.emit()
                return
            
            # Create output folder
            os.makedirs(self.output_folder, exist_ok=True)
            
            # Open source PDF
            self.progress.emit(5, "Opening PDF...")
            source_doc = fitz.open(self.pdf_path)
            total_pages = len(source_doc)
            
            if total_pages == 0:
                self.error.emit("PDF has no pages")
                source_doc.close()
                return
            
            # Create blank page if needed with dynamic dimensions
            blank_path = None
            # Need blank if: manual add_blank OR (odd/even with odd pages - always)
            need_blank = self.add_blank or (self.split_mode == "odd_even" and total_pages % 2 != 0)

            if need_blank:
                target_width, target_height = self._get_target_page_dimensions()
                blank_doc = fitz.open()
                blank_doc.new_page(width=target_width, height=target_height)
                blank_path = os.path.join(self.output_folder, "_temp_blank.pdf")
                blank_doc.save(blank_path)
                blank_doc.close()
                del blank_doc
                gc.collect()
            
            split_files = []
            
            if self.split_mode == "odd_even":
                # Odd/Even split
                self.progress.emit(10, "Splitting into odd and even pages...")
                
                # Odd pages
                odd_doc = fitz.open()
                for page_num in range(0, total_pages, 2):
                    if self._cancelled:
                        odd_doc.close()
                        source_doc.close()
                        self.progress.emit(0, "Split cancelled")
                        self.finished.emit()
                        return
                    odd_doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)
                
                # Blank pages will be added later if reverse_split is enabled
                # Otherwise add them now
                if self.add_blank and blank_path and not self.reverse_split:
                    blank_temp = fitz.open(blank_path)
                    odd_doc.insert_pdf(blank_temp)
                    blank_temp.close()
                
                odd_path = os.path.join(self.output_folder, f"{self.base_name}_odd.pdf")
                odd_doc.save(odd_path)
                odd_doc.close()
                split_files.append(odd_path)
                
                self.progress.emit(50, "Creating odd pages PDF...")
                
                # Even pages
                even_doc = fitz.open()
                for page_num in range(1, total_pages, 2):
                    if self._cancelled:
                        even_doc.close()
                        source_doc.close()
                        self.progress.emit(0, "Split cancelled")
                        self.finished.emit()
                        return
                    even_doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)

                # Add manual blank if requested and not reversing
                if self.add_blank and blank_path and not self.reverse_split:
                    blank_temp = fitz.open(blank_path)
                    even_doc.insert_pdf(blank_temp)
                    blank_temp.close()

                even_path = os.path.join(self.output_folder, f"{self.base_name}_even.pdf")

                # Add auto-blank to even PDF if odd total pages and NOT reversing
                # (if reversing, it will be added after reverse)
                if total_pages % 2 != 0 and not self.reverse_split and blank_path:
                    blank_temp = fitz.open(blank_path)
                    even_doc.insert_pdf(blank_temp)
                    blank_temp.close()

                even_doc.save(even_path)
                even_doc.close()
                split_files.append(even_path)
                
                self.progress.emit(90, "Creating even pages PDF...")
                
            elif self.split_mode == "custom":
                # Custom ranges split
                num_ranges = len(self.custom_ranges)
                padding_width = len(str(num_ranges))
                
                for range_idx, (from_page, to_page) in enumerate(self.custom_ranges):
                    if self._cancelled:
                        source_doc.close()
                        self.progress.emit(0, "Split cancelled")
                        self.finished.emit()
                        return
                    
                    progress_pct = 10 + int((range_idx / num_ranges) * 80)
                    self.progress.emit(
                        progress_pct,
                        f"Creating range {range_idx + 1}/{num_ranges} (pages {from_page}-{to_page})..."
                    )
                    
                    # Convert to 0-based indexing for PyMuPDF
                    start_page = from_page - 1
                    end_page = to_page - 1
                    
                    # Validate range
                    if start_page < 0 or end_page >= total_pages:
                        self.error.emit(f"Invalid range: pages {from_page}-{to_page} exceeds PDF bounds")
                        source_doc.close()
                        return
                    
                    range_doc = fitz.open()
                    range_doc.insert_pdf(source_doc, from_page=start_page, to_page=end_page)
                    
                    # Blank pages will be added later if reverse_split is enabled
                    # Otherwise add them now
                    if self.add_blank and blank_path and not self.reverse_split:
                        blank_temp = fitz.open(blank_path)
                        range_doc.insert_pdf(blank_temp)
                        blank_temp.close()
                    
                    range_path = os.path.join(
                        self.output_folder,
                        f"{self.base_name}_range_{range_idx + 1:0{padding_width}d}_pages_{from_page}-{to_page}.pdf"
                    )
                    range_doc.save(range_path)
                    range_doc.close()
                    split_files.append(range_path)
                    
                    QThread.msleep(1)
                    gc.collect()
                
            else:  # Range-based split
                num_splits = (total_pages + self.pages_per_split - 1) // self.pages_per_split
                
                for split_idx in range(num_splits):
                    if self._cancelled:
                        source_doc.close()
                        self.progress.emit(0, "Split cancelled")
                        self.finished.emit()
                        return
                    
                    start_page = split_idx * self.pages_per_split
                    end_page = min(start_page + self.pages_per_split - 1, total_pages - 1)
                    
                    progress_pct = 10 + int((split_idx / num_splits) * 80)
                    self.progress.emit(
                        progress_pct, 
                        f"Creating split {split_idx + 1}/{num_splits} (pages {start_page + 1}-{end_page + 1})..."
                    )
                    
                    split_doc = fitz.open()
                    split_doc.insert_pdf(source_doc, from_page=start_page, to_page=end_page)
                    
                    # Blank pages will be added later if reverse_split is enabled
                    # Otherwise add them now
                    if self.add_blank and blank_path and not self.reverse_split:
                        blank_temp = fitz.open(blank_path)
                        split_doc.insert_pdf(blank_temp)
                        blank_temp.close()
                    
                    # Calculate padding width based on total number of splits
                    padding_width = len(str(num_splits))
                    split_path = os.path.join(self.output_folder, f"{self.base_name}_part_{split_idx + 1:0{padding_width}d}.pdf")
                    split_doc.save(split_path)
                    split_doc.close()
                    split_files.append(split_path)
                    
                    QThread.msleep(1)
                    gc.collect()
            
            source_doc.close()
            
            # Handle reverse split (reverse pages inside AND reverse file order)
            if self.reverse_split and len(split_files) > 0:
                self.progress.emit(95, "Reversing pages in each split PDF...")
                
                # STEP 1: Reverse pages inside each PDF
                for idx, pdf_path in enumerate(split_files):
                    if self._cancelled:
                        self.progress.emit(0, "Split cancelled")
                        self.finished.emit()
                        return
                    
                    # Open the PDF
                    pdf_doc = fitz.open(pdf_path)
                    num_pages = len(pdf_doc)
                    
                    # Reverse the page order
                    reversed_pages = list(range(num_pages - 1, -1, -1))
                    pdf_doc.select(reversed_pages)
                    
                    # Save to temporary file, then replace original
                    temp_path = pdf_path + ".tmp"
                    pdf_doc.save(temp_path)
                    pdf_doc.close()
                    
                    # Replace original with reversed version
                    os.remove(pdf_path)
                    os.rename(temp_path, pdf_path)
                    
                    gc.collect()
                
                # STEP 2: Add blank pages AFTER reversing
                if self.split_mode == "odd_even" and total_pages % 2 != 0 and not self.add_blank:
                    # Auto-blank for odd/even: only add to Even PDF (second file)
                    self.progress.emit(96, "Adding blank page to even PDF...")
                    
                    if len(split_files) >= 2 and blank_path:  # Make sure we have both odd and even
                        # Only add blank to Even PDF (index 1)
                        pdf_path = split_files[1]
                        
                        if self._cancelled:
                            self.progress.emit(0, "Split cancelled")
                            self.finished.emit()
                            return
                        
                        pdf_doc = fitz.open(pdf_path)
                        blank_temp = fitz.open(blank_path)
                        pdf_doc.insert_pdf(blank_temp)
                        blank_temp.close()
                        
                        temp_path = pdf_path + ".tmp"
                        pdf_doc.save(temp_path)
                        pdf_doc.close()
                        
                        os.remove(pdf_path)
                        os.rename(temp_path, pdf_path)
                        
                        gc.collect()

                elif self.add_blank and blank_path:
                    # Manual blank: add to ALL split files
                    self.progress.emit(96, "Adding blank pages after reversal...")
                    
                    for idx, pdf_path in enumerate(split_files):
                        if self._cancelled:
                            self.progress.emit(0, "Split cancelled")
                            self.finished.emit()
                            return
                        
                        pdf_doc = fitz.open(pdf_path)
                        blank_temp = fitz.open(blank_path)
                        pdf_doc.insert_pdf(blank_temp)
                        blank_temp.close()
                        
                        temp_path = pdf_path + ".tmp"
                        pdf_doc.save(temp_path)
                        pdf_doc.close()
                        
                        os.remove(pdf_path)
                        os.rename(temp_path, pdf_path)
                        
                        gc.collect()
                
                # STEP 3: Reverse file order (only if multiple files)
                if len(split_files) > 1:
                    self.progress.emit(97, "Reversing file order...")
                    
                    temp_files = []
                    for idx, original_path in enumerate(split_files):
                        temp_path = original_path + ".tmp"
                        os.rename(original_path, temp_path)
                        temp_files.append(temp_path)
                    
                    reversed_files = list(reversed(temp_files))
                    for new_idx, temp_path in enumerate(reversed_files):
                        if self.split_mode == "custom":
                            final_path = temp_path.replace(".tmp", "")
                        elif self.split_mode == "odd_even":
                            final_path = temp_path.replace(".tmp", "")
                        else:
                            # Calculate padding width based on original number of splits for reverse order
                            padding_width = len(str(len(split_files)))
                            final_path = os.path.join(
                                self.output_folder, 
                                f"{self.base_name}_part_{new_idx + 1:0{padding_width}d}.pdf"
                            )
                        os.rename(temp_path, final_path)
            
            # Cleanup
            if blank_path and os.path.exists(blank_path):
                try:
                    os.remove(blank_path)
                except:
                    pass
            
            self.progress.emit(100, "Split complete!")
            self.success.emit(self.output_folder, len(split_files))
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            gc.collect()
            self.finished.emit()


class PDFScanWorker(QObject):
    """Worker for scanning PDF folder in background thread"""
    finished = Signal()
    progress = Signal(int, int)  # current, total
    completed = Signal(list)  # pdf_files_data
    error = Signal(str)

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        """Scan folder for PDFs and get page counts"""
        try:
            pdf_files = []
            
            # First pass: collect all PDF filenames
            all_files = [f for f in os.listdir(self.folder_path) if f.lower().endswith('.pdf')]
            total_files = len(all_files)
            
            if total_files == 0:
                self.completed.emit([])
                self.finished.emit()
                return
            
            # Second pass: open each PDF and get page count
            for idx, file in enumerate(all_files, 1):
                pdf_path = os.path.join(self.folder_path, file)
                
                try:
                    # Open PDF to get page count
                    doc = fitz.open(pdf_path)
                    page_count = len(doc)
                    doc.close()
                    
                    pdf_files.append({
                        'name': file,
                        'path': pdf_path,
                        'pages': page_count,
                        'included': True
                    })
                except Exception:
                    # If can't open, add with 0 pages
                    pdf_files.append({
                        'name': file,
                        'path': pdf_path,
                        'pages': 0,
                        'included': True
                    })
                
                # Emit progress every file (or every 10 files for large batches)
                if idx % 10 == 0 or idx == total_files:
                    self.progress.emit(idx, total_files)
            
            # Sort by name
            pdf_files.sort(key=lambda x: x['name'])
            
            # Emit results
            self.completed.emit(pdf_files)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class PDFDimensionCheckWorker(QObject):
    """Worker for checking PDF dimensions in background thread"""
    finished = Signal()
    error = Signal(str)
    success = Signal(dict)  # payload with results

    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        try:
            try:
                # Import dimension checking functions
                from .pdf_page_dimension_checker import (
                    check_folder_pdf_dimensions, format_points_to_mm,
                )
            except Exception:
                from pages.merge_split.pdf_page_dimension_checker import (
                    check_folder_pdf_dimensions, format_points_to_mm,
                )

            all_same, ref_size, differing, file_main = check_folder_pdf_dimensions(self.folder_path)
            payload = {
                "all_same": all_same,
                "ref_size": ref_size,
                "differing": differing,
                "file_main": file_main,
                # Path-indexed helpers for robust UI matching
                "file_main_by_path": {os.path.join(self.folder_path, k): v for k, v in file_main.items()},
                "differing_paths": [os.path.join(self.folder_path, k) for k in differing],
            }
            # Also include formatted strings to reduce GUI work
            payload["ref_mm"] = format_points_to_mm(ref_size) if ref_size != (0, 0) else ""
            self.success.emit(payload)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


if __name__ == "__main__":
    # Test the section standalone
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    w = PDFSplitSection()
    w.setWindowTitle("PDF Desk - Preview")
    w.resize(1000, 600)
    w.show()
    sys.exit(app.exec())
