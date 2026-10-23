import os
import json
from pathlib import Path
import fitz  # PyMuPDF for rendering previews

from PySide6.QtCore import Qt, QRectF, QPointF, QThread, Signal, QObject
from PySide6.QtGui import QPixmap, QImage, QBrush, QColor, QPen, QFontDatabase, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QFileDialog, QSpinBox, QMessageBox, QListWidget, QListWidgetItem,
    QSlider, QGraphicsView, QGraphicsScene, QGraphicsRectItem, QScrollArea, QComboBox, QRadioButton, QButtonGroup, QCheckBox, QDoubleSpinBox
)
from concurrent.futures import ThreadPoolExecutor, as_completed

# Performance optimization imports
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("[Performance] psutil not available - using basic CPU-based threading")

class PDFColourConversionSection(QWidget):
    """
    Standalone UI section for "PDF PREP" consistent with app.py styling.

    Purpose:
      - Let the user define base settings for downstream colour conversion flows
      - Persist configuration to config/config.json

    Config schema (aligned with existing tools like pdf_selector_gui):
      {
        "settings": {
          "input_path": "<folder-or-file>",
          "dpi": 300,
          "max_workers": 4,
          "batch_size": 25
        },
        "regions": []
      }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_dir = Path("config")
        self.config_path = self.config_dir / "config.json"
        try:
            self._ensure_google_sans()
        except Exception:
            pass

        # UI state
        self.input_path_edit = None
        self.x_dpi_spin = None
        self.y_dpi_spin = None
        # Removed user-configurable controls for max workers and batch size
        self.status_label = None

        # Preview/graphics
        self.graphics_view = None
        self.graphics_scene = None
        self.page_pixmap_item = None
        self.page_pixmap = None
        self._view_mode = 'regions'  # 'regions' or 'converted'
        self.converted_doc = None
        self.converted_pdf_path = None
        self.converted_total_pages = 0
        self.converted_current_page = 0

        # Region drawing state
        self._drawing = False
        self._start_pos = QPointF()
        self._temp_rect_item = None

        # Regions data and UI
        self.regions = []  # list of dicts {name, coordinates[4], cmyk[4], priority, items{rect,label}}
        self.regions_list = None
        # Folder list item label mapping and exclusions
        self.folder_item_labels = {}
        self.excluded_paths = set()

        # CMYK controls
        self.c_slider = None
        self.m_slider = None
        self.y_slider = None
        self.k_slider = None
        self.color_preview = None

        self._init_ui()
        # Preload if config exists
        self._load_config_if_present()
        # Ensure initial state
        self._set_preview_mode('regions')

    # --- UI -----------------------------------------------------------------
    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Top header row with sticky Start Stage 1 button (fixed at top-right)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 20, 0)  # right padding to sit a bit left
        header_row.addStretch(1)
        # Right column: Start button + progress + status stacked
        header_right_col = QVBoxLayout()
        self.start_stage1_btn = QPushButton("START")
        self.start_stage1_btn.setMinimumHeight(40)
        self.start_stage1_btn.setMinimumWidth(140)
        self.start_stage1_btn.setStyleSheet("""
            QPushButton { background-color:#28a745; color:white; font-weight:600; font-size:12pt; padding:10px 16px; border:none; border-radius:6px; }
            QPushButton:hover { background-color:#218838; }
            QPushButton:disabled { background-color:#8fd19e; }
        """)
        self.start_stage1_btn.clicked.connect(self._start_stage1_process)
        header_btns = QHBoxLayout()
        header_btns.addStretch(1)
        header_btns.addWidget(self.start_stage1_btn)
        # STOP button next to START
        self.stop_stage_btn = QPushButton("STOP")
        self.stop_stage_btn.setMinimumHeight(40)
        self.stop_stage_btn.setMinimumWidth(120)
        self.stop_stage_btn.setEnabled(False)
        self.stop_stage_btn.setStyleSheet("""
            QPushButton { background-color:#dc3545; color:white; font-weight:600; font-size:12pt; padding:10px 16px; border:none; border-radius:6px; }
            QPushButton:hover { background-color:#c82333; }
            QPushButton:disabled { background-color:#f5b5bd; }
        """)
        self.stop_stage_btn.clicked.connect(self._stop_stage_processing)
        header_btns.addWidget(self.stop_stage_btn)
        header_right_col.addLayout(header_btns)
        # Progress bar just below the Start button
        from PySide6.QtWidgets import QProgressBar
        self.conv_progress = QProgressBar()
        self.conv_progress.setVisible(False)
        self.conv_progress.setMinimum(0)
        self.conv_progress.setMaximum(0)
        header_right_col.addWidget(self.conv_progress)
        # Status label below progress
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        header_right_col.addWidget(self.status_label, 0, Qt.AlignLeft)
        header_row.addLayout(header_right_col)
        layout.addLayout(header_row)

        # Main content area with scroll (like pdf_split_section.py)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)

        # (Removed top title/info group as requested)

        # Configuration
        cfg_group = QGroupBox("Folder Selection")
        self._style_group_box(cfg_group)
        cfg_layout = QVBoxLayout()
        cfg_layout.setSpacing(15)  # Add spacing between sections within Configuration

        # Input path (folder or a single PDF)
        cfg_layout.addWidget(QLabel("Select input folder"))
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setPlaceholderText("Select input folder or a single PDF file…")
        browse_row = QHBoxLayout()
        browse_row.addWidget(self.input_path_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_input)
        browse_row.addWidget(browse_btn)
        cfg_layout.addLayout(browse_row)
        # Record a standard button width based on Browse… button
        try:
            self.standard_button_width = browse_btn.sizeHint().width()
        except Exception:
            self.standard_button_width = None

        # Output path (final PDFs destination for Stage 1/2)
        cfg_layout.addWidget(QLabel("Select output folder"))
        output_row = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("Select output folder for final PDFs…")
        output_row.addWidget(self.output_path_edit)
        output_browse_btn = QPushButton("Browse…")
        output_browse_btn.clicked.connect(self._browse_output_global)
        output_row.addWidget(output_browse_btn)
        cfg_layout.addLayout(output_row)

        # Folder PDFs listing
        folder_group = QGroupBox("Folder PDFs")
        self._style_group_box(folder_group)
        folder_v = QVBoxLayout()
        folder_info = QLabel("If an input folder is selected, all PDFs will be listed below with page counts.")
        folder_info.setStyleSheet("color: #6c757d; font-size: 9pt;")
        folder_info.setWordWrap(True)
        folder_v.addWidget(folder_info)
        self.folder_pdf_list = QListWidget()
        try:
            self.folder_pdf_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        self.folder_pdf_list.setSelectionMode(QListWidget.SingleSelection)
        self.folder_pdf_list.currentRowChanged.connect(self._on_folder_selection_changed)
        folder_v.addWidget(self.folder_pdf_list)
        # Dimensions result label (populated after folder browse)
        self.folder_dim_label = QLabel("")
        self.folder_dim_label.setStyleSheet("color: #495057; font-size: 9pt;")
        self.folder_dim_label.setWordWrap(True)
        folder_v.addWidget(self.folder_dim_label)
        folder_group.setLayout(folder_v)
        cfg_layout.addWidget(folder_group)

        # DPI moved to Preview Settings group
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("X DPI:"))
        self.x_dpi_spin = QSpinBox()
        self.x_dpi_spin.setRange(72, 2400)
        self.x_dpi_spin.setValue(300)
        self.x_dpi_spin.setEnabled(False)
        dpi_row.addWidget(self.x_dpi_spin)
        dpi_row.addWidget(QLabel("Y DPI:"))
        self.y_dpi_spin = QSpinBox()
        self.y_dpi_spin.setRange(72, 2400)
        self.y_dpi_spin.setValue(300)
        self.y_dpi_spin.setEnabled(False)
        dpi_row.addWidget(self.y_dpi_spin)
        dpi_row.addStretch(1)

        # Removed Max workers and Batch size controls from UI

        # Load preview button (will be placed in Regions group)
        load_preview_btn = QPushButton("Load Preview")
        load_preview_btn.clicked.connect(self._load_pdf_preview)

        # PDF Scaling section
        scaling_group = QGroupBox("PDF Scaling")
        # Store reference to group box for styling
        self.scaling_group_box = scaling_group
        scaling_layout = QVBoxLayout()
        # Title row with enable checkbox
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("PDF Scaling"))
        title_row.addStretch(1)
        self.scaling_enabled_cb = QCheckBox("Enable")
        self.scaling_enabled_cb.setChecked(False)  # Start unchecked
        self.scaling_enabled_cb.stateChanged.connect(self._on_scaling_enabled_changed)
        # Style enable checkbox to green when checked
        try:
            self._style_enable_checkbox(self.scaling_enabled_cb)
        except Exception:
            pass
        title_row.addWidget(self.scaling_enabled_cb)
        scaling_layout.addLayout(title_row)
        
        # Target size in millimeters (absolute scaling)
        scaling_row = QHBoxLayout()
        scaling_row.addWidget(QLabel("Target size:"))
        self.scale_width_mm = QSpinBox()
        self.scale_width_mm.setRange(10, 10000)
        self.scale_width_mm.setSuffix(" mm")
        self.scale_width_mm.setEnabled(False)
        self.scale_width_mm.setValue(210)  # default A4 width mm
        scaling_row.addWidget(self.scale_width_mm)
        scaling_row.addWidget(QLabel("×"))
        self.scale_height_mm = QSpinBox()
        self.scale_height_mm.setRange(10, 10000)
        self.scale_height_mm.setSuffix(" mm")
        self.scale_height_mm.setEnabled(False)
        self.scale_height_mm.setValue(297)  # default A4 height mm
        scaling_row.addWidget(self.scale_height_mm)
        scaling_row.addStretch(1)
        scaling_layout.addLayout(scaling_row)
        
        # Scaling info
        scaling_info = QLabel("Scale pages to exact dimensions (width × height in mm)")
        scaling_info.setStyleSheet("color: #6c757d; font-size: 9pt;")
        scaling_info.setWordWrap(True)
        scaling_layout.addWidget(scaling_info)
        
        # SET button for scaling (right-aligned, width matches Browse)
        set_scaling_btn = QPushButton("SET")
        set_scaling_btn.clicked.connect(self._set_scaling_config)
        self.set_scaling_btn = set_scaling_btn
        self.set_scaling_btn.setEnabled(False)
        try:
            if getattr(self, 'standard_button_width', None):
                set_scaling_btn.setFixedWidth(self.standard_button_width)
        except Exception:
            pass
        set_scaling_row = QHBoxLayout()
        set_scaling_row.addStretch(1)
        set_scaling_row.addWidget(set_scaling_btn)
        scaling_layout.addLayout(set_scaling_row)
        
        scaling_group.setLayout(scaling_layout)

        # PDF Margin Adjustment section
        margin_group = QGroupBox("PDF Margin Adjustment")
        # Store reference to group box for styling
        self.margin_group_box = margin_group
        margin_layout = QVBoxLayout()
        # Title row with enable checkbox
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("PDF Margin Adjustment"))
        title_row.addStretch(1)
        self.margin_enabled_cb = QCheckBox("Enable")
        self.margin_enabled_cb.setChecked(False)  # Start unchecked
        self.margin_enabled_cb.stateChanged.connect(self._on_margin_enabled_changed)
        try:
            self._style_enable_checkbox(self.margin_enabled_cb)
        except Exception:
            pass
        title_row.addWidget(self.margin_enabled_cb)
        margin_layout.addLayout(title_row)
        
        # Margin info
        margin_info = QLabel("Adjust margins for all PDFs in the input folder (in millimeters)")
        margin_info.setStyleSheet("color: #6c757d; font-size: 9pt;")
        margin_info.setWordWrap(True)
        margin_layout.addWidget(margin_info)
        
        # Top margin
        top_margin_row = QHBoxLayout()
        top_label = QLabel("Top margin:")
        top_label.setStyleSheet("color: #000000;")
        top_margin_row.addWidget(top_label)
        self.top_margin_spin = QDoubleSpinBox()
        self.top_margin_spin.setDecimals(2)
        self.top_margin_spin.setRange(-100.0, 100.0)
        self.top_margin_spin.setSingleStep(0.01)
        self.top_margin_spin.setValue(0.00)
        self.top_margin_spin.setSuffix(" mm")
        self.top_margin_spin.setEnabled(False)
        self.top_margin_spin.setStyleSheet("color: #000000;")
        top_margin_row.addWidget(self.top_margin_spin)
        top_margin_row.addStretch(1)
        margin_layout.addLayout(top_margin_row)
        
        # Bottom margin
        bottom_margin_row = QHBoxLayout()
        bottom_label = QLabel("Bottom margin:")
        bottom_label.setStyleSheet("color: #000000;")
        bottom_margin_row.addWidget(bottom_label)
        self.bottom_margin_spin = QDoubleSpinBox()
        self.bottom_margin_spin.setDecimals(2)
        self.bottom_margin_spin.setRange(-100.0, 100.0)
        self.bottom_margin_spin.setSingleStep(0.01)
        self.bottom_margin_spin.setValue(0.00)
        self.bottom_margin_spin.setSuffix(" mm")
        self.bottom_margin_spin.setEnabled(False)
        self.bottom_margin_spin.setStyleSheet("color: #000000;")
        bottom_margin_row.addWidget(self.bottom_margin_spin)
        bottom_margin_row.addStretch(1)
        margin_layout.addLayout(bottom_margin_row)
        
        # Left margin
        left_margin_row = QHBoxLayout()
        left_label = QLabel("Left margin:")
        left_label.setStyleSheet("color: #000000;")
        left_margin_row.addWidget(left_label)
        self.left_margin_spin = QDoubleSpinBox()
        self.left_margin_spin.setDecimals(2)
        self.left_margin_spin.setRange(-100.0, 100.0)
        self.left_margin_spin.setSingleStep(0.01)
        self.left_margin_spin.setValue(0.00)
        self.left_margin_spin.setSuffix(" mm")
        self.left_margin_spin.setEnabled(False)
        self.left_margin_spin.setStyleSheet("color: #000000;")
        left_margin_row.addWidget(self.left_margin_spin)
        left_margin_row.addStretch(1)
        margin_layout.addLayout(left_margin_row)
        
        # Right margin
        right_margin_row = QHBoxLayout()
        right_label = QLabel("Right margin:")
        right_label.setStyleSheet("color: #000000;")
        right_margin_row.addWidget(right_label)
        self.right_margin_spin = QDoubleSpinBox()
        self.right_margin_spin.setDecimals(2)
        self.right_margin_spin.setRange(-100.0, 100.0)
        self.right_margin_spin.setSingleStep(0.01)
        self.right_margin_spin.setValue(0.00)
        self.right_margin_spin.setSuffix(" mm")
        self.right_margin_spin.setEnabled(False)
        self.right_margin_spin.setStyleSheet("color: #000000;")
        right_margin_row.addWidget(self.right_margin_spin)
        right_margin_row.addStretch(1)
        margin_layout.addLayout(right_margin_row)
        
        # Margin info
        margin_note = QLabel("Negative values = trim margins, Positive values = add margins")
        margin_note.setStyleSheet("color: #6c757d; font-size: 8pt; font-style: italic;")
        margin_note.setWordWrap(True)
        margin_layout.addWidget(margin_note)
        
        # SET button for margin adjustment (right-aligned, width matches Browse)
        set_margin_btn = QPushButton("SET")
        set_margin_btn.clicked.connect(self._set_margin_config)
        self.set_margin_btn = set_margin_btn
        self.set_margin_btn.setEnabled(False)
        try:
            if getattr(self, 'standard_button_width', None):
                set_margin_btn.setFixedWidth(self.standard_button_width)
        except Exception:
            pass
        set_margin_row = QHBoxLayout()
        set_margin_row.addStretch(1)
        set_margin_row.addWidget(set_margin_btn)
        margin_layout.addLayout(set_margin_row)
        
        margin_group.setLayout(margin_layout)

        # Add Blank Pages section (separate box)
        append_group = QGroupBox("Add Blank Pages")
        # Store reference to group box for styling
        self.append_group_box = append_group
        append_layout = QVBoxLayout()
        # Title row with enable checkbox
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Add Blank Pages"))
        title_row.addStretch(1)
        self.append_enabled_cb = QCheckBox("Enable")
        self.append_enabled_cb.setChecked(False)  # Start unchecked
        self.append_enabled_cb.stateChanged.connect(self._on_append_enabled_changed)
        try:
            self._style_enable_checkbox(self.append_enabled_cb)
        except Exception:
            pass
        title_row.addWidget(self.append_enabled_cb)
        append_layout.addLayout(title_row)
        append_row1 = QHBoxLayout()
        append_row1.addWidget(QLabel("Append blank pages:"))
        self.append_pages_spin = QSpinBox()
        self.append_pages_spin.setRange(1, 999)
        self.append_pages_spin.setValue(1)
        self.append_pages_spin.setMaximumWidth(70)
        self.append_pages_spin.setEnabled(False)
        append_row1.addWidget(self.append_pages_spin)
        self.append_mode_combo = QComboBox()
        self.append_mode_combo.addItems(["At end", "After page…", "Alternate (after every page)"])
        self.append_mode_combo.currentIndexChanged.connect(self._on_append_mode_changed)
        self.append_mode_combo.setMinimumContentsLength(10)
        self.append_mode_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.append_mode_combo.setEnabled(False)
        append_row1.addWidget(self.append_mode_combo, 1)
        append_layout.addLayout(append_row1)

        append_row2 = QHBoxLayout()
        self.append_after_label = QLabel("After page:")
        self.append_after_label.setVisible(False)
        append_row2.addWidget(self.append_after_label)
        self.append_after_page_spin = QSpinBox()
        self.append_after_page_spin.setRange(1, 99999)
        self.append_after_page_spin.setValue(1)
        self.append_after_page_spin.setMaximumWidth(80)
        self.append_after_page_spin.setEnabled(False)
        append_row2.addWidget(self.append_after_page_spin)
        append_row2.addStretch(1)
        append_layout.addLayout(append_row2)
        
        # SET button for append pages (right-aligned, width matches Browse)
        set_append_btn = QPushButton("SET")
        set_append_btn.clicked.connect(self._set_append_config)
        self.set_append_btn = set_append_btn
        self.set_append_btn.setEnabled(False)
        try:
            if getattr(self, 'standard_button_width', None):
                set_append_btn.setFixedWidth(self.standard_button_width)
        except Exception:
            pass
        set_append_row = QHBoxLayout()
        set_append_row.addStretch(1)
        set_append_row.addWidget(set_append_btn)
        append_layout.addLayout(set_append_row)
        
        append_group.setLayout(append_layout)

        cfg_group.setLayout(cfg_layout)
        content_layout.addWidget(cfg_group)

        # Rotation group
        rotate_group = QGroupBox("Rotate Pages")
        # Store reference to group box for styling
        self.rotate_group_box = rotate_group
        rotate_layout = QVBoxLayout()
        # Title row with enable checkbox
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Rotate Pages"))
        title_row.addStretch(1)
        self.rotate_enabled_cb = QCheckBox("Enable")
        self.rotate_enabled_cb.setChecked(False)  # Start unchecked
        self.rotate_enabled_cb.stateChanged.connect(self._on_rotate_enabled_changed)
        try:
            self._style_enable_checkbox(self.rotate_enabled_cb)
        except Exception:
            pass
        title_row.addWidget(self.rotate_enabled_cb)
        rotate_layout.addLayout(title_row)
        rotate_info = QLabel("Rotate every page of selected PDFs by one of the chosen angles")
        rotate_info.setStyleSheet("color: #6c757d; font-size: 9pt;")
        rotate_info.setWordWrap(True)
        rotate_layout.addWidget(rotate_info)
        rot_row = QHBoxLayout()
        self.rot_group = QButtonGroup(self)
        self.rot_group.setExclusive(True)
        self.rot_0 = QRadioButton("0°")
        self.rot_90 = QRadioButton("90°")
        self.rot_180 = QRadioButton("180°")
        self.rot_270 = QRadioButton("270°")
        self.rot_group.addButton(self.rot_0, 0)
        self.rot_group.addButton(self.rot_90, 90)
        self.rot_group.addButton(self.rot_180, 180)
        self.rot_group.addButton(self.rot_270, 270)
        self.rot_0.setChecked(True)
        # Start with all controls disabled (unchecked by default)
        self.rot_0.setEnabled(False)
        self.rot_90.setEnabled(False)
        self.rot_180.setEnabled(False)
        self.rot_270.setEnabled(False)
        rot_row.addWidget(self.rot_0)
        rot_row.addWidget(self.rot_90)
        rot_row.addWidget(self.rot_180)
        rot_row.addWidget(self.rot_270)
        rot_row.addStretch(1)
        rotate_layout.addLayout(rot_row)
        
        # SET button for rotation (right-aligned like Browse button)
        set_rotate_btn = QPushButton("SET")
        set_rotate_btn.clicked.connect(self._set_rotation_config)
        self.set_rotate_btn = set_rotate_btn
        self.set_rotate_btn.setEnabled(False)
        # Match width to standard Browse button if available
        try:
            if getattr(self, 'standard_button_width', None):
                set_rotate_btn.setFixedWidth(self.standard_button_width)
        except Exception:
            pass
        set_row = QHBoxLayout()
        set_row.addStretch(1)
        set_row.addWidget(set_rotate_btn)
        rotate_layout.addLayout(set_row)
        
        rotate_group.setLayout(rotate_layout)
        content_layout.addWidget(rotate_group)

        # Reverse Ordering group
        reverse_group = QGroupBox("Reverse Ordering")
        # Store reference to group box for styling
        self.reverse_group_box = reverse_group
        reverse_layout = QVBoxLayout()
        # Title row with enable checkbox
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Reverse Ordering"))
        title_row.addStretch(1)
        self.reverse_enabled_cb = QCheckBox("Enable")
        self.reverse_enabled_cb.setChecked(False)  # Start unchecked
        self.reverse_enabled_cb.stateChanged.connect(self._on_reverse_enabled_changed)
        try:
            self._style_enable_checkbox(self.reverse_enabled_cb)
        except Exception:
            pass
        title_row.addWidget(self.reverse_enabled_cb)
        reverse_layout.addLayout(title_row)
        reverse_info = QLabel("Reverse pages in each selected PDF (last to first)")
        reverse_info.setStyleSheet("color: #6c757d; font-size: 9pt;")
        reverse_info.setWordWrap(True)
        reverse_layout.addWidget(reverse_info)
        
        # SET button for reverse ordering (right-aligned, width matches Browse)
        set_reverse_btn = QPushButton("SET")
        set_reverse_btn.clicked.connect(self._set_reverse_config)
        self.set_reverse_btn = set_reverse_btn
        self.set_reverse_btn.setEnabled(False)
        try:
            if getattr(self, 'standard_button_width', None):
                set_reverse_btn.setFixedWidth(self.standard_button_width)
        except Exception:
            pass
        set_reverse_row = QHBoxLayout()
        set_reverse_row.addStretch(1)
        set_reverse_row.addWidget(set_reverse_btn)
        reverse_layout.addLayout(set_reverse_row)
        
        reverse_group.setLayout(reverse_layout)
        content_layout.addWidget(reverse_group)

        # Preview Settings group (DPI + Load Preview)
        preview_settings_group = QGroupBox("DPI (Stage 1)")
        # Store reference to group box for styling
        self.dpi_group_box = preview_settings_group
        preview_settings_layout = QVBoxLayout()
        # Title row with enable checkbox
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("DPI Settings (Applied after Color Conversion)"))
        title_row.addStretch(1)
        self.dpi_enabled_cb = QCheckBox("Enable")
        self.dpi_enabled_cb.setChecked(False)  # Start unchecked
        self.dpi_enabled_cb.stateChanged.connect(self._on_dpi_enabled_changed)
        try:
            self._style_enable_checkbox(self.dpi_enabled_cb)
        except Exception:
            pass
        title_row.addWidget(self.dpi_enabled_cb)
        preview_settings_layout.addLayout(title_row)
        preview_settings_layout.addLayout(dpi_row)
        
        # SET button for DPI (right-aligned, width matches Browse)
        set_dpi_btn = QPushButton("SET")
        set_dpi_btn.clicked.connect(self._set_dpi_config)
        self.set_dpi_btn = set_dpi_btn
        self.set_dpi_btn.setEnabled(False)
        try:
            if getattr(self, 'standard_button_width', None):
                set_dpi_btn.setFixedWidth(self.standard_button_width)
        except Exception:
            pass
        set_dpi_row = QHBoxLayout()
        set_dpi_row.addStretch(1)
        set_dpi_row.addWidget(set_dpi_btn)
        preview_settings_layout.addLayout(set_dpi_row)
        
        preview_settings_group.setLayout(preview_settings_layout)
        content_layout.addWidget(preview_settings_group)

        # Add Blank Pages group
        content_layout.addWidget(append_group)

        # Now place Scaling and Margin groups after
        content_layout.addWidget(scaling_group)
        content_layout.addWidget(margin_group)

        # Add vertical spacing before Colour Conversion section title
        content_layout.addSpacing(20)

        # Toggle button to show/hide the Colour Conversion section
        toggle_row = QHBoxLayout()
        self.colour_toggle_btn = QPushButton("🚫 Show Colour Conversion (disabled)")
        self.colour_toggle_btn.setCheckable(True)
        self.colour_toggle_btn.setChecked(False)
        self.colour_toggle_btn.setEnabled(False)
        self.colour_toggle_btn.clicked.connect(self._toggle_colour_conversion_section)
        try:
            self.colour_toggle_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #adb5bd;
                    color: #495057;
                    font-weight: 600;
                    padding: 6px 14px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: #adb5bd;
                }
                QPushButton:checked {
                    background-color: #adb5bd;
                }
                """
            )
        except Exception:
            pass
        toggle_row.addWidget(self.colour_toggle_btn, 0, Qt.AlignLeft)
        toggle_row.addStretch(1)
        content_layout.addLayout(toggle_row)

        # Create container for Colour Conversion controls and preview
        self.colour_conversion_container = QWidget()
        controls_preview_layout = QHBoxLayout(self.colour_conversion_container)
        controls_preview_layout.setContentsMargins(0, 0, 0, 0)
        controls_preview_layout.setSpacing(20)
        
        # Left side: Colour Conversion section (CMYK + Regions + Actions)
        controls_group = QGroupBox("Colour Conversion")
        self._style_group_box(controls_group)
        try:
            controls_group.setStyleSheet(
                """
                QGroupBox {
                    font-weight: bold;
                    font-size: 16pt;
                    color: #212529;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    margin-top: 30px; /* extra space above title */
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0 8px;
                    background: transparent;
                    font-weight: bold;
                    font-size: 16pt;
                    color: #000000;
                }
                """
            )
        except Exception:
            pass
        # Store reference to Controls group box for enabling/disabling
        self.controls_group_box = controls_group
        controls_v = QVBoxLayout()

        # Colour Conversion I/O inside Controls
        cc_io_group = QGroupBox("Colour Conversion - Input/Output")
        self._style_group_box(cc_io_group)
        cc_io_v = QVBoxLayout()

        # Input folder row (separate from top Configuration for convenience)
        cc_in_row = QHBoxLayout()
        self.cc_input_edit = QLineEdit()
        self.cc_input_edit.setPlaceholderText("Choose input folder containing PDFs…")
        self.cc_input_edit.textChanged.connect(lambda _: self._update_start_conv_enabled())
        cc_in_row.addWidget(self.cc_input_edit)
        cc_browse_in_btn = QPushButton("Browse…")
        cc_browse_in_btn.clicked.connect(self._browse_input_cc)
        cc_in_row.addWidget(cc_browse_in_btn)
        cc_io_v.addLayout(cc_in_row)

        # PDFs list (click to preview)
        self.cc_pdf_list = QListWidget()
        try:
            self.cc_pdf_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        self.cc_pdf_list.itemClicked.connect(self._on_cc_pdf_clicked)
        cc_io_v.addWidget(self.cc_pdf_list)

        # Output folder row
        cc_out_row = QHBoxLayout()
        self.cc_output_edit = QLineEdit()
        self.cc_output_edit.setPlaceholderText("Choose output folder for coloured PDFs…")
        self.cc_output_edit.textChanged.connect(lambda _: self._update_start_conv_enabled())
        cc_out_row.addWidget(self.cc_output_edit)
        cc_browse_out_btn = QPushButton("Browse…")
        cc_browse_out_btn.clicked.connect(self._browse_output_cc)
        cc_out_row.addWidget(cc_browse_out_btn)
        cc_io_v.addLayout(cc_out_row)

        cc_io_group.setLayout(cc_io_v)
        controls_v.addWidget(cc_io_group)

        # Color Change section header (no enable/disable needed)
        color_header = QLabel("Color Change (CMYK)")
        color_header.setStyleSheet("font-weight: bold; font-size: 11pt; color: #212529; margin-bottom: 5px;")
        controls_v.addWidget(color_header)

        # CMYK sliders
        cmyk_group = QGroupBox("CMYK Color")
        self._style_group_box(cmyk_group)
        cmyk_v = QVBoxLayout()
        self.c_slider = self._make_cmyk_slider("Cyan:")
        self.m_slider = self._make_cmyk_slider("Magenta:")
        self.y_slider = self._make_cmyk_slider("Yellow:")
        self.k_slider = self._make_cmyk_slider("Black:")
        for row in (self.c_slider, self.m_slider, self.y_slider, self.k_slider):
            cmyk_v.addLayout(row[0])
        self.color_preview = QLabel()
        self.color_preview.setFixedHeight(32)
        self.color_preview.setStyleSheet("background:#00ffff; border:1px solid #ced4da; border-radius:3px;")
        cmyk_v.addWidget(self.color_preview)
        cmyk_group.setLayout(cmyk_v)
        controls_v.addWidget(cmyk_group)

        # Regions list
        regions_group = QGroupBox("Regions")
        self._style_group_box(regions_group)
        regions_v = QVBoxLayout()
        self.regions_list = QListWidget()
        try:
            self.regions_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        self.regions_list.currentRowChanged.connect(self._on_region_selected)
        regions_v.addWidget(self.regions_list)

        regions_btn_row = QHBoxLayout()
        del_btn = QPushButton("Delete Region")
        del_btn.clicked.connect(self._delete_region)
        clr_btn = QPushButton("Clear All")
        clr_btn.clicked.connect(self._clear_regions)
        regions_btn_row.addWidget(del_btn)
        regions_btn_row.addWidget(clr_btn)
        regions_v.addLayout(regions_btn_row)
        # Move Load Preview button here (below delete/clear, above Save Config)
        regions_v.addWidget(load_preview_btn)

        # Save Config button
        save_btn = QPushButton("Save Config")
        save_btn.clicked.connect(self._save_config)
        regions_v.addWidget(save_btn)
        regions_group.setLayout(regions_v)
        controls_v.addWidget(regions_group, 1)

        # Actions
        actions_group = QGroupBox("Actions")
        # Store reference to Controls group box (not Actions) for color enable/disable
        self.color_group_box = controls_group  # controls_group is the Controls group box
        actions_layout = QVBoxLayout()
        # Start Conversion button
        start_btn = QPushButton("Start Conversion")
        start_btn.clicked.connect(self._start_colour_conversion)
        self.start_conversion_btn = start_btn
        self.start_conversion_btn.setEnabled(False)
        actions_layout.addWidget(start_btn)
        # Show converted preview (kept for internal references but not shown)
        show_conv_btn = QPushButton("Show Converted Preview")
        show_conv_btn.clicked.connect(self._select_converted_pdf)
        self.show_converted_btn = show_conv_btn
        actions_group.setLayout(actions_layout)
        controls_v.addWidget(actions_group)

        controls_group.setLayout(controls_v)
        
        # Right side: PDF Preview section (no title)
        preview_group = QGroupBox("")
        self._style_group_box(preview_group)
        preview_main_layout = QVBoxLayout()
        
        # Navigation controls
        nav_row = QHBoxLayout()
        self.preview_file_label = QLabel("")
        self.preview_file_label.setStyleSheet("color:#6c757d;")
        nav_row.addWidget(self.preview_file_label, 1)
        nav_row.addWidget(QLabel("Page:"))
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setEnabled(False)
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        nav_row.addWidget(self.page_spin)
        self.prev_page_btn = QPushButton("Prev")
        self.prev_page_btn.setEnabled(False)
        self.prev_page_btn.clicked.connect(lambda: self._goto_converted_page(self.converted_current_page))
        nav_row.addWidget(self.prev_page_btn)
        self.next_page_btn = QPushButton("Next")
        self.next_page_btn.setEnabled(False)
        self.next_page_btn.clicked.connect(lambda: self._goto_converted_page(self.converted_current_page + 2))
        nav_row.addWidget(self.next_page_btn)
        preview_main_layout.addLayout(nav_row)
        
        # Graphics view for region drawing and preview
        self.graphics_scene = QGraphicsScene(self)
        self.graphics_view = _RegionGraphicsView(self)
        self.graphics_view.setScene(self.graphics_scene)
        self.graphics_view.setRenderHints(self.graphics_view.renderHints())
        self.graphics_view.setMouseTracking(True)
        self.graphics_view.setMinimumHeight(400)  # Set minimum height for preview
        preview_main_layout.addWidget(self.graphics_view)
        
        preview_group.setLayout(preview_main_layout)
        
        # Add both sections to horizontal layout
        controls_preview_layout.addWidget(controls_group, 1)  # Left side - Controls
        controls_preview_layout.addWidget(preview_group, 2)   # Right side - Preview (larger)

        # Add the container widget to the main content layout (hidden by default)
        self.colour_conversion_container.setVisible(False)
        content_layout.addWidget(self.colour_conversion_container)

        # (Progress bar and status moved to sticky header under Start)

        # (START STAGE 1 button moved to sticky header row)
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 1)
        
        # NOW apply initial styling - after all widgets are fully initialized
        self._apply_initial_styling()

        # Initialize Start Conversion button state
        self._update_start_conv_enabled()

    def _toggle_colour_conversion_section(self, checked: bool):
        """Show or hide the Colour Conversion section based on toggle button state."""
        if hasattr(self, "colour_conversion_container"):
            self.colour_conversion_container.setVisible(checked)
        if hasattr(self, "colour_toggle_btn"):
            self.colour_toggle_btn.setText(
                "Hide Colour Conversion" if checked else "Show Colour Conversion"
            )

    # --- Handlers ------------------------------------------------------------
    def _browse_input(self):
        # Offer both file and directory selection, preferring a directory picker first
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder", os.getcwd())
        if folder:
            self.input_path_edit.setText(folder)
            try:
                self._refresh_folder_pdf_list(folder)
            except Exception:
                pass
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF", os.getcwd(), "PDF Files (*.pdf)")
        if file_path:
            self.input_path_edit.setText(file_path)
            # Do not auto-load here; user can click Load Preview

    # --- Controls (Colour Conversion) I/O helpers ---------------------------
    def _browse_input_cc(self):
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Input Folder (Colour Conversion)", os.getcwd())
            if folder:
                self.cc_input_edit.setText(folder)
                self._populate_cc_pdf_list(folder)
                self._update_start_conv_enabled()
        except Exception:
            pass

    def _browse_output_cc(self):
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Output Folder (Coloured PDFs)", os.getcwd())
            if folder:
                self.cc_output_edit.setText(folder)
                self._update_start_conv_enabled()
        except Exception:
            pass

    def _populate_cc_pdf_list(self, folder_path: str):
        try:
            self.cc_pdf_list.clear()
            if not os.path.isdir(folder_path):
                return
            pdfs = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith('.pdf')]
            for name in pdfs:
                full = os.path.join(folder_path, name)
                item = QListWidgetItem(f"{name}")
                item.setData(Qt.UserRole, full)
                item.setToolTip(full)
                self.cc_pdf_list.addItem(item)
        except Exception:
            pass

    def _on_cc_pdf_clicked(self, item: QListWidgetItem):
        try:
            pdf_path = item.data(Qt.UserRole)
            if pdf_path and os.path.isfile(pdf_path):
                self._load_preview_from_path(pdf_path)
        except Exception:
            pass

    def _load_preview_from_path(self, pdf_path: str):
        try:
            self._set_preview_mode('regions')
            if not pdf_path.lower().endswith('.pdf') or not os.path.exists(pdf_path):
                return
            import fitz
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                doc.close()
                return
            page = doc[0]
            from .render_utils import qimage_from_page, clamp_dpi
            # Force preview to use current UI spins, but default to 300 if disabled
            xdpi = clamp_dpi(300)
            ydpi = clamp_dpi(300)
            qimg = qimage_from_page(page, xdpi, ydpi)
            self.page_pixmap = QPixmap.fromImage(qimg)
            self.graphics_scene.clear()
            self.page_pixmap_item = self.graphics_scene.addPixmap(self.page_pixmap)
            self.graphics_scene.setSceneRect(QRectF(self.page_pixmap.rect()))
            self.graphics_view.fitInView(self.graphics_scene.sceneRect(), Qt.KeepAspectRatio)
            self._redraw_regions()
            doc.close()
            self.status_label.setText(f"Loaded preview: {Path(pdf_path).name}")
            self.preview_file_label.setText(f"Preview: {Path(pdf_path).name}")
        except Exception:
            pass

    def _update_start_conv_enabled(self):
        try:
            # Accept either Controls input folder or main Configuration path
            cc_input = ''
            cfg_input = ''
            if hasattr(self, 'cc_input_edit') and self.cc_input_edit.text().strip():
                cc_input = self.cc_input_edit.text().strip()
            if hasattr(self, 'input_path_edit') and self.input_path_edit.text().strip():
                cfg_input = self.input_path_edit.text().strip()

            # Determine if there is at least one PDF to process
            def has_pdfs_in_folder(path: str) -> bool:
                try:
                    return any(f.lower().endswith('.pdf') for f in os.listdir(path))
                except Exception:
                    return False

            has_list_cc = hasattr(self, 'cc_pdf_list') and self.cc_pdf_list.count() > 0
            has_list_cfg = hasattr(self, 'folder_pdf_list') and self.folder_pdf_list.count() > 0

            # Input may be a single PDF file
            single_pdf_ok = False
            candidate = cc_input or cfg_input
            if candidate and os.path.isfile(candidate) and candidate.lower().endswith('.pdf'):
                single_pdf_ok = True

            # Input may be a folder with PDFs
            folder_has_pdfs = False
            if candidate and os.path.isdir(candidate):
                folder_has_pdfs = has_list_cc or has_list_cfg or has_pdfs_in_folder(candidate)

            input_available = bool(candidate and (single_pdf_ok or folder_has_pdfs))

            # Do NOT require explicit output; we'll default if missing
            self.start_conversion_btn.setEnabled(bool(input_available))
        except Exception:
            try:
                self.start_conversion_btn.setEnabled(False)
            except Exception:
                pass

    def _refresh_folder_pdf_list(self, folder_path: str):
        self.folder_pdf_list.clear()
        self.folder_item_labels.clear()
        if not os.path.isdir(folder_path):
            return
        try:
            import fitz
        except Exception:
            QMessageBox.warning(self, "Missing Dependency", "PyMuPDF (fitz) is required to read page counts.")
            return
        pdfs = [f for f in sorted(os.listdir(folder_path)) if f.lower().endswith('.pdf')]
        for name in pdfs:
            full = os.path.join(folder_path, name)
            try:
                doc = fitz.open(full)
                n = len(doc)
                doc.close()
                item = QListWidgetItem()
                item.setData(Qt.UserRole, full)
                item.setData(Qt.UserRole + 1, n)
                item.setToolTip(full)
                # Build item widget: label + spacer + red cross button
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(4, 0, 4, 0)
                row_layout.setSpacing(6)
                label = QLabel(f"{name}    (pages: {n}) — ? × ? mm")
                row_layout.addWidget(label, 1)
                btn = QPushButton("✕")
                btn.setFixedSize(22, 22)
                try:
                    btn.setFlat(True)
                    btn.setAutoDefault(False)
                    btn.setDefault(False)
                    btn.setFocusPolicy(Qt.NoFocus)
                except Exception:
                    pass
                btn.setStyleSheet(
                    "QPushButton{color:#dc3545;font-weight:bold;background:transparent;border:none;padding:0;}"
                    "QPushButton:hover{background:rgba(220,53,69,0.08);border-radius:3px;}"
                    "QPushButton:pressed{background:rgba(220,53,69,0.18);border-radius:3px;}"
                )
                btn.setToolTip("Exclude this PDF from processing")
                btn.clicked.connect(lambda _, p=full: self._exclude_pdf(p))
                row_layout.addWidget(btn, 0)
                self.folder_pdf_list.addItem(item)
                self.folder_pdf_list.setItemWidget(item, row_widget)
                self.folder_item_labels[full] = label
            except Exception:
                item = QListWidgetItem()
                item.setData(Qt.UserRole, full)
                item.setData(Qt.UserRole + 1, None)
                item.setToolTip(full)
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(4, 0, 4, 0)
                row_layout.setSpacing(6)
                label = QLabel(f"{name}    (pages: ?) — ? × ? mm")
                row_layout.addWidget(label, 1)
                btn = QPushButton("✕")
                btn.setFixedSize(22, 22)
                try:
                    btn.setFlat(True)
                    btn.setAutoDefault(False)
                    btn.setDefault(False)
                    btn.setFocusPolicy(Qt.NoFocus)
                except Exception:
                    pass
                btn.setStyleSheet(
                    "QPushButton{color:#dc3545;font-weight:bold;background:transparent;border:none;padding:0;}"
                    "QPushButton:hover{background:rgba(220,53,69,0.08);border-radius:3px;}"
                    "QPushButton:pressed{background:rgba(220,53,69,0.18);border-radius:3px;}"
                )
                btn.setToolTip("Exclude this PDF from processing")
                btn.clicked.connect(lambda _, p=full: self._exclude_pdf(p))
                row_layout.addWidget(btn, 0)
                self.folder_pdf_list.addItem(item)
                self.folder_pdf_list.setItemWidget(item, row_widget)
                self.folder_item_labels[full] = label

        # After listing, run dimensions check in background and update label via signal
        try:
            self.folder_dim_label.setText("Checking page sizes…")
            self.folder_dim_label.setStyleSheet("color: #6c757d;")
        except Exception:
            pass

        # Cancel/cleanup any previous dimension thread
        try:
            if hasattr(self, 'dim_thread') and self.dim_thread is not None:
                # Let it finish naturally; we will ignore late results by path check
                pass
        except Exception:
            pass

        self.dim_thread = QThread()
        self.dim_worker = _PDFDimensionCheckWorker(folder_path=folder_path)
        self.dim_worker.moveToThread(self.dim_thread)
        self.dim_thread.started.connect(self.dim_worker.run)
        self.dim_worker.finished.connect(self.dim_thread.quit)
        self.dim_worker.finished.connect(self.dim_worker.deleteLater)
        self.dim_thread.finished.connect(self.dim_thread.deleteLater)
        self.dim_worker.error.connect(self._on_dim_error)
        self.dim_worker.success.connect(self._on_dim_success)
        self.dim_thread.start()

    def _append_blank_pages_selected(self):
        src = self.input_path_edit.text().strip()
        if not src or not os.path.isdir(src):
            QMessageBox.warning(self, "No Folder", "Please select an input folder containing PDFs.")
            return
        item = self.folder_pdf_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Please select a PDF from the list.")
            return
        pdf_path = item.data(Qt.UserRole)
        total_pages = item.data(Qt.UserRole + 1) or 0
        num_pages = int(self.append_pages_spin.value())
        mode_index = int(self.append_mode_combo.currentIndex())
        after_page = int(self.append_after_page_spin.value()) if mode_index == 1 else -1
        # Clamp after_page to a valid range if pages known
        if mode_index == 1 and total_pages:
            if after_page < 1:
                after_page = 1
            if after_page > total_pages:
                after_page = total_pages
        # Fixed output folder under app directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        out_dir = os.path.join(script_dir, "appended_pdfs")
        os.makedirs(out_dir, exist_ok=True)
        # Disable UI bits
        self.append_btn.setEnabled(False)
        self.conv_progress.setVisible(True)
        self.conv_progress.setMaximum(0)
        self.status_label.setText("Appending blank pages...")
        # Background worker
        self.append_thread = QThread()
        self.append_worker = _PDFAppendBlankWorker(
            pdf_path=pdf_path,
            output_dir=out_dir,
            pages_to_append=num_pages,
            mode=mode_index,
            after_page=after_page
        )
        self.append_worker.moveToThread(self.append_thread)
        self.append_thread.started.connect(self.append_worker.run)
        self.append_worker.finished.connect(self.append_thread.quit)
        self.append_worker.finished.connect(self.append_worker.deleteLater)
        self.append_thread.finished.connect(self.append_thread.deleteLater)
        self.append_worker.error.connect(self._on_append_error)
        self.append_worker.success.connect(self._on_append_success)
        self.append_worker.progress.connect(self._on_append_progress)
        self.append_thread.start()

    def _on_append_progress(self, msg: str):
        self.status_label.setText(msg)

    def _on_append_error(self, msg: str):
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.append_btn.setEnabled(True)
        QMessageBox.critical(self, "Append Failed", msg)
        self.status_label.setText(f"Error: {msg}")

    def _on_append_success(self, out_path: str):
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.append_btn.setEnabled(True)
        QMessageBox.information(self, "Append Complete", f"Saved: {out_path}")
        self.status_label.setText(f"Append complete: {os.path.basename(out_path)}")

    def _on_dim_error(self, msg: str):
        try:
            self.folder_dim_label.setText("Page size check failed")
            self.folder_dim_label.setStyleSheet("color: #dc3545; font-weight: 500;")
        except Exception:
            pass

    def _on_dim_success(self, payload: dict):
        try:
            # If user navigated away or label missing, ignore
            if not hasattr(self, 'folder_dim_label') or self.folder_dim_label is None:
                return
            all_same = payload.get("all_same", False)
            ref_size = payload.get("ref_size", (0, 0))
            ref_mm = payload.get("ref_mm", "")
            differing = payload.get("differing", [])
            file_main = payload.get("file_main", {})

            if all_same and ref_size != (0, 0):
                self.folder_dim_label.setText(f"All PDFs/pages share the same size: {ref_mm}")
                self.folder_dim_label.setStyleSheet("color: #198754; font-weight: 500;")
            else:
                if not differing:
                    self.folder_dim_label.setText("Could not determine consistent page sizes.")
                    self.folder_dim_label.setStyleSheet("color: #dc3545; font-weight: 500;")
                else:
                    # Show up to first 6 differing files, then summarize
                    max_show = 6
                    shown = differing[:max_show]
                    rest = len(differing) - len(shown)
                    parts = []
                    for fname in shown:
                        sz = file_main.get(fname, (0, 0))
                        parts.append(f"{fname}")
                    more = f" and {rest} more" if rest > 0 else ""
                    self.folder_dim_label.setText("Different sizes detected: " + ", ".join(parts) + more)
                    self.folder_dim_label.setStyleSheet("color: #fd7e14; font-weight: 500;")

            # Update list items: append size and highlight differing ones in red
            try:
                from PySide6.QtGui import QColor
            except Exception:
                QColor = None

            # Prefer path-indexed results to avoid name collisions and ensure exact match
            file_main_by_path = payload.get("file_main_by_path", {})
            differing_paths = set(payload.get("differing_paths", []))

            for row in range(self.folder_pdf_list.count()):
                item = self.folder_pdf_list.item(row)
                full_path = item.data(Qt.UserRole)
                pages = item.data(Qt.UserRole + 1)
                name = os.path.basename(full_path) if full_path else ""
                # Lookup by full path first, fallback to name
                size_pt = file_main_by_path.get(full_path)
                if size_pt is None:
                    size_pt = file_main.get(name, (0, 0))
                size_mm = self._format_points_to_mm(size_pt) if size_pt != (0, 0) else "? × ? mm"
                pages_text = pages if isinstance(pages, int) else "?"
                # Update label on item widget
                label = self.folder_item_labels.get(full_path)
                if label is not None:
                    label.setText(f"{name}    (pages: {pages_text}) — {size_mm}")
                is_diff = (full_path in differing_paths) or (name in differing)
                if is_diff and QColor is not None:
                    try:
                        if label is not None:
                            label.setStyleSheet("color: rgb(220,53,69);")
                    except Exception:
                        pass
                else:
                    try:
                        if label is not None:
                            label.setStyleSheet("color: rgb(33,37,41);")
                    except Exception:
                        pass
        except Exception:
            pass

    def _apply_initial_styling(self):
        """Apply initial faded styling to all features since they start unchecked"""
        try:
            # Apply faded styling to all 7 features (they start unchecked/disabled)
            self._apply_group_styling(False, "rotate")
            self._apply_group_styling(False, "reverse")
            self._apply_group_styling(False, "append")
            self._apply_group_styling(False, "scaling")
            self._apply_group_styling(False, "margin")
            self._apply_group_styling(False, "dpi")
            # Controls (Color) is always available; keep normal styling
            self._apply_group_styling(True, "color")
        except Exception:
            pass

    def _on_rotate_enabled_changed(self, state):
        enabled = bool(state)
        print(f"Rotate enabled changed: state={state}, enabled={enabled}")  # DEBUG
        self.rot_0.setEnabled(enabled)
        self.rot_90.setEnabled(enabled)
        self.rot_180.setEnabled(enabled)
        self.rot_270.setEnabled(enabled)
        self.set_rotate_btn.setEnabled(enabled)
        print(f"After setEnabled - rot_0 enabled: {self.rot_0.isEnabled()}")  # DEBUG
        # Update rotation config - always update enabled state
        if not hasattr(self, 'rotation_config'):
            self.rotation_config = {"enabled": enabled, "angle": 0}
        else:
            self.rotation_config["enabled"] = enabled
        self._apply_group_styling(enabled, "rotate")
        self._update_processing_config()

    def _on_reverse_enabled_changed(self, state):
        enabled = bool(state)
        self.set_reverse_btn.setEnabled(enabled)
        # Update reverse config - always update enabled state
        if not hasattr(self, 'reverse_config'):
            self.reverse_config = {"enabled": enabled}
        else:
            self.reverse_config["enabled"] = enabled
        self._apply_group_styling(enabled, "reverse")
        self._update_processing_config()

    def _on_append_enabled_changed(self, state):
        enabled = bool(state)
        self.append_pages_spin.setEnabled(enabled)
        self.append_mode_combo.setEnabled(enabled)
        self.append_after_page_spin.setEnabled(enabled and self.append_mode_combo.currentIndex() == 1)
        self.set_append_btn.setEnabled(enabled)
        # Update append config - always update enabled state
        if not hasattr(self, 'append_config'):
            self.append_config = {"enabled": enabled, "pages": 1, "mode": 0, "after_page": -1}
        else:
            self.append_config["enabled"] = enabled
        self._apply_group_styling(enabled, "append")
        self._update_processing_config()

    def _on_scaling_enabled_changed(self, state):
        enabled = bool(state)
        self.scale_width_mm.setEnabled(enabled)
        self.scale_height_mm.setEnabled(enabled)
        self.set_scaling_btn.setEnabled(enabled)
        # Update scaling config - always update enabled state
        if not hasattr(self, 'scaling_config'):
            self.scaling_config = {"enabled": enabled, "target_width_mm": 210, "target_height_mm": 297}
        else:
            self.scaling_config["enabled"] = enabled
        self._apply_group_styling(enabled, "scaling")
        self._update_processing_config()

    def _on_margin_enabled_changed(self, state):
        enabled = bool(state)
        self.top_margin_spin.setEnabled(enabled)
        self.bottom_margin_spin.setEnabled(enabled)
        self.left_margin_spin.setEnabled(enabled)
        self.right_margin_spin.setEnabled(enabled)
        self.set_margin_btn.setEnabled(enabled)
        # Update margin config - always update enabled state
        if not hasattr(self, 'margin_config'):
            self.margin_config = {"enabled": enabled, "top": 0, "bottom": 0, "left": 0, "right": 0}
        else:
            self.margin_config["enabled"] = enabled
        self._apply_group_styling(enabled, "margin")
        self._update_processing_config()

    def _on_dpi_enabled_changed(self, state):
        enabled = bool(state)
        self.x_dpi_spin.setEnabled(enabled)
        self.y_dpi_spin.setEnabled(enabled)
        self.set_dpi_btn.setEnabled(enabled)
        # Update DPI config - always update enabled state
        if not hasattr(self, 'dpi_config'):
            self.dpi_config = {
                "enabled": enabled,
                "x_dpi": self.x_dpi_spin.value(),
                "y_dpi": self.y_dpi_spin.value()
            }
        else:
            self.dpi_config["enabled"] = enabled
            self.dpi_config["x_dpi"] = self.x_dpi_spin.value()
            self.dpi_config["y_dpi"] = self.y_dpi_spin.value()
        self._apply_group_styling(enabled, "dpi")
        self._update_processing_config()


    # --- SET Button Handlers -------------------------------------------------
    def _set_rotation_config(self):
        """Save rotation configuration when SET button is clicked"""
        angle = self.rot_group.checkedId()
        self.status_label.setText(f"Rotation set to {angle}°")
        # Store the configuration for later use
        self.rotation_config = {"enabled": True, "angle": angle}
        self._update_processing_config()
        try:
            QMessageBox.information(self, "Rotation", f"Rotation set to {angle}°")
        except Exception:
            pass

    def _set_reverse_config(self):
        """Save reverse ordering configuration when SET button is clicked"""
        self.status_label.setText("Reverse ordering configuration set")
        # Store the configuration for later use
        self.reverse_config = {"enabled": True}
        self._update_processing_config()
        try:
            QMessageBox.information(self, "Reverse Ordering", "Reverse ordering enabled")
        except Exception:
            pass

    def _set_append_config(self):
        """Save append pages configuration when SET button is clicked"""
        pages = self.append_pages_spin.value()
        mode = self.append_mode_combo.currentIndex()
        after_page = self.append_after_page_spin.value() if mode == 1 else -1
        self.status_label.setText(f"Append {pages} pages configuration set")
        # Store the configuration for later use
        self.append_config = {
            "enabled": True,
            "pages": pages,
            "mode": mode,
            "after_page": after_page
        }
        self._update_processing_config()
        try:
            mode_text = ["at end", "after page", "alternate after every page"][mode]
            extra = f" {after_page}" if mode == 1 else ""
            QMessageBox.information(self, "Add Blank Pages", f"Will append {pages} page(s) {mode_text}{extra}")
        except Exception:
            pass

    def _set_scaling_config(self):
        """Save scaling configuration when SET button is clicked"""
        tw = int(self.scale_width_mm.value())
        th = int(self.scale_height_mm.value())
        self.status_label.setText(f"Scaling target set to {tw} × {th} mm")
        # Store the configuration for later use
        self.scaling_config = {"enabled": True, "target_width_mm": tw, "target_height_mm": th}
        self._update_processing_config()
        try:
            QMessageBox.information(self, "Scaling", f"Target size set: {tw} × {th} mm")
        except Exception:
            pass

    def _set_margin_config(self):
        """Save margin adjustment configuration when SET button is clicked"""
        top = float(self.top_margin_spin.value())
        bottom = float(self.bottom_margin_spin.value())
        left = float(self.left_margin_spin.value())
        right = float(self.right_margin_spin.value())
        self.status_label.setText(f"Margins set: T:{top:.2f} B:{bottom:.2f} L:{left:.2f} R:{right:.2f} mm")
        # Store the configuration for later use
        self.margin_config = {
            "enabled": True,
            "top": top,
            "bottom": bottom,
            "left": left,
            "right": right
        }
        self._update_processing_config()
        try:
            QMessageBox.information(self, "Margins", f"Set margins (mm) T:{top:.2f} B:{bottom:.2f} L:{left:.2f} R:{right:.2f}")
        except Exception:
            pass

    def _set_dpi_config(self):
        """Save DPI configuration when SET button is clicked"""
        x_dpi = self.x_dpi_spin.value()
        y_dpi = self.y_dpi_spin.value()
        self.status_label.setText(f"DPI set for Stage 1: X:{x_dpi} Y:{y_dpi} (applied before scaling and margins)")
        # Store the configuration for later use
        self.dpi_config = {
            "enabled": True,
            "x_dpi": x_dpi,
            "y_dpi": y_dpi
        }
        self._update_processing_config()
        try:
            QMessageBox.information(self, "DPI", f"DPI set: X {x_dpi}, Y {y_dpi}")
        except Exception:
            pass

    def _start_stage1_process(self):
        """Start Stage 1 processing (DPI → Scaling → Margins) for selected PDFs"""
        try:
            # Read processing config
            processing_config_path = self.config_dir / "processing_config.json"
            if not processing_config_path.exists():
                QMessageBox.warning(self, "No Config", "Please configure and save settings first using SET buttons.")
                return
            
            with processing_config_path.open('r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Get Stage 1 operations
            stage1 = config.get("processing_sequence", {}).get("stage_1", {})
            operations = stage1.get("operations", {})
            
            # Check if any Stage 1 operations are enabled
            dpi_enabled = operations.get("dpi_adjustment", {}).get("enabled", False)
            scaling_enabled = operations.get("page_scaling", {}).get("enabled", False)
            margin_enabled = operations.get("pdf_margin_adjustment", {}).get("enabled", False)
            stage1_operations_enabled = dpi_enabled or scaling_enabled or margin_enabled
            
            # Get input path and selected files
            input_path = self.input_path_edit.text().strip()
            if not input_path:
                QMessageBox.warning(self, "No Input", "Please select an input folder or PDF file.")
                return
            
            # Get selected files from folder list (respect exclusions) with folder fallback
            include_files = []
            if os.path.isdir(input_path):
                excluded = getattr(self, 'excluded_paths', set())
                # Prefer curated list if available
                if self.folder_pdf_list and self.folder_pdf_list.count() > 0:
                    for i in range(self.folder_pdf_list.count()):
                        item = self.folder_pdf_list.item(i)
                        if item:
                            file_path = item.data(Qt.UserRole)
                            if file_path and os.path.isfile(file_path) and file_path not in excluded:
                                include_files.append(file_path)
                else:
                    # Fallback: scan directory for PDFs
                    try:
                        for name in sorted(os.listdir(input_path)):
                            if name.lower().endswith('.pdf'):
                                p = os.path.join(input_path, name)
                                if p not in excluded and os.path.isfile(p):
                                    include_files.append(p)
                    except Exception:
                        pass
            
            if not include_files and os.path.isfile(input_path):
                include_files = [input_path]
            
            if not include_files:
                QMessageBox.warning(self, "No Files", "No PDF files selected for processing.")
                return
            
            # Confirmation popup summarizing enabled settings (only enabled, no stage headings)
            try:
                stage1_ops = operations
                stage2 = config.get("processing_sequence", {}).get("stage_2", {})
                stage2_ops = stage2.get("operations", {})

                lines = []
                lines.append("Input: " + (input_path if len(input_path) < 100 else (input_path[:97] + "…")))
                out_sel = self.output_path_edit.text().strip() if hasattr(self, 'output_path_edit') else ''
                lines.append("Output folder: " + (out_sel or "<not selected>"))
                lines.append("")
                any_enabled = False
                if stage1_ops.get("dpi_adjustment", {}).get("enabled", False):
                    x1 = stage1_ops.get("dpi_adjustment", {}).get("x_dpi", 300)
                    y1 = stage1_ops.get("dpi_adjustment", {}).get("y_dpi", 300)
                    lines.append(f"• DPI: X {x1}, Y {y1}")
                    any_enabled = True
                if stage1_ops.get("page_scaling", {}).get("enabled", False):
                    ps = stage1_ops.get("page_scaling", {})
                    tw = ps.get("target_width_mm")
                    th = ps.get("target_height_mm")
                    if isinstance(tw, (int, float)) and isinstance(th, (int, float)):
                        lines.append(f"• Scaling: {int(tw)} × {int(th)} mm")
                    else:
                        lines.append("• Scaling: <target size not set>")
                    any_enabled = True
                if stage1_ops.get("pdf_margin_adjustment", {}).get("enabled", False):
                    m = stage1_ops.get("pdf_margin_adjustment", {})
                    t = float(m.get('top_margin', 0))
                    b = float(m.get('bottom_margin', 0))
                    l = float(m.get('left_margin', 0))
                    r = float(m.get('right_margin', 0))
                    lines.append(
                        f"• Margins: T {t:.2f}  B {b:.2f}  L {l:.2f}  R {r:.2f} mm"
                    )
                    any_enabled = True

                if stage2_ops.get("rotation", {}).get("enabled", False):
                    ang = stage2_ops.get("rotation", {}).get("angle", 0)
                    lines.append(f"• Rotation: {ang}°")
                    any_enabled = True
                if stage2_ops.get("reverse_ordering", {}).get("enabled", False):
                    lines.append("• Reverse ordering")
                    any_enabled = True
                if stage2_ops.get("add_blank_pages", {}).get("enabled", False):
                    ap = stage2_ops.get("add_blank_pages", {})
                    mode_map = {0: "at end", 1: "after page", 2: "alternate"}
                    mode_text = mode_map.get(ap.get("mode", 0), "at end")
                    after_p = ap.get("after_page", -1)
                    extra = f" {after_p}" if ap.get("mode", 0) == 1 else ""
                    lines.append(f"• Add blank pages: {ap.get('pages_to_append',1)} {mode_text}{extra}")
                    any_enabled = True

                if not any_enabled:
                    lines.append("• No transformations enabled")

                summary = "\n".join(lines)
                reply = QMessageBox.question(
                    self,
                    "Confirm Processing",
                    summary + "\n\nProceed?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply != QMessageBox.Yes:
                    return
            except Exception:
                pass

            # Setup output directories
            script_dir = os.path.dirname(os.path.abspath(__file__))
            temp_folder_1 = os.path.join(script_dir, "TEMP_FOLDER_1")
            temp_folder_2 = os.path.join(script_dir, "TEMP_FOLDER_2")
            # Determine final output folder from global selector
            final_output_folder = ''
            try:
                if hasattr(self, 'output_path_edit') and self.output_path_edit.text().strip():
                    final_output_folder = self.output_path_edit.text().strip()
            except Exception:
                pass
            if not final_output_folder:
                QMessageBox.warning(self, "No Output Folder", "Please select an output folder for final PDFs.")
                return
            # Keep for Stage 2 or copy after Stage 1
            self._selected_final_output = final_output_folder
            
            # Clean up existing files in output folders
            import shutil
            if os.path.exists(temp_folder_1):
                shutil.rmtree(temp_folder_1)
            if os.path.exists(temp_folder_2):
                shutil.rmtree(temp_folder_2)
                
            os.makedirs(temp_folder_1, exist_ok=True)
            os.makedirs(temp_folder_2, exist_ok=True)
            
            # Disable UI and show progress
            self.start_stage1_btn.setEnabled(False)
            self.conv_progress.setVisible(True)
            self.conv_progress.setMaximum(0)
            
            if stage1_operations_enabled:
                # Run Stage 1 first, then Stage 2
                self.status_label.setText("Starting Stage 1 processing...")
                
                # Start Stage 1 worker thread
                self.stage1_thread = QThread()
                self.stage1_worker = _Stage1ProcessingWorker(
                    include_files=include_files,
                    output_folder=temp_folder_1,
                    config=config
                )
                self.stage1_worker.moveToThread(self.stage1_thread)
                
                self.stage1_thread.started.connect(self.stage1_worker.run)
                self.stage1_worker.finished.connect(self.stage1_thread.quit)
                self.stage1_worker.finished.connect(self.stage1_worker.deleteLater)
                self.stage1_thread.finished.connect(self.stage1_thread.deleteLater)
                self.stage1_worker.progress.connect(self._on_stage1_progress)
                self.stage1_worker.error.connect(self._on_stage1_error)
                self.stage1_worker.success.connect(self._on_stage1_success)
                
                # Store config for Stage 2
                self._pending_stage2_config = config
                self._pending_stage2_files = include_files
                self._pending_stage2_final_folder = final_output_folder
                
                # Lower thread priority to keep GUI responsive under heavy CPU
                try:
                    self.stage1_thread.setPriority(QThread.LowestPriority)
                except Exception:
                    pass
                self.stage1_thread.start()
                # Enable STOP while running
                try:
                    self.stop_stage_btn.setEnabled(True)
                except Exception:
                    pass
            else:
                # Skip Stage 1, go directly to Stage 2 with source files
                self.status_label.setText("Skipping Stage 1, starting Stage 2 directly...")
                self._start_stage2_processing(include_files, config, input_path, final_output_folder)
            
        except Exception as e:
            QMessageBox.critical(self, "Stage 1 Error", f"Failed to start Stage 1 processing: {e}")
            self.start_stage1_btn.setEnabled(True)
            self.conv_progress.setVisible(False)

    def _on_stage1_progress(self, message: str):
        """Handle Stage 1 progress updates"""
        self.status_label.setText(message)

    def _on_stage1_error(self, message: str):
        """Handle Stage 1 errors"""
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_stage1_btn.setEnabled(True)
        try:
            self.stop_stage_btn.setEnabled(False)
        except Exception:
            pass
        QMessageBox.critical(self, "Stage 1 Failed", message)
        self.status_label.setText(f"Error: {message}")

    def _on_stage1_success(self, output_folder: str):
        """Handle Stage 1 completion and start Stage 2"""
        self.status_label.setText("Stage 1 complete, starting Stage 2...")
        try:
            self.stop_stage_btn.setEnabled(False)
        except Exception:
            pass
        
        # Start Stage 2 with Stage 1 output as input
        if hasattr(self, '_pending_stage2_config') and hasattr(self, '_pending_stage2_files'):
            # Use Stage 1 output folder as input for Stage 2
            final_folder = getattr(self, '_pending_stage2_final_folder', None) or getattr(self, '_selected_final_output', None) or os.path.join(os.path.dirname(os.path.abspath(__file__)), "FINAL_OUTPUT_FOLDER")
            self._start_stage2_processing(self._pending_stage2_files, self._pending_stage2_config, output_folder, final_folder)
        else:
            # Fallback - just show completion message
            self.conv_progress.setVisible(False)
            self.conv_progress.setMaximum(100)
            self.start_stage1_btn.setEnabled(True)
            QMessageBox.information(self, "Stage 1 Complete", f"Stage 1 processing completed successfully!\nOutput saved to: {os.path.basename(output_folder)}")
            self.status_label.setText(f"Stage 1 completed: {os.path.basename(output_folder)}")

    def _start_stage2_processing(self, include_files, config, input_folder, final_output_folder):
        """Start Stage 2 processing (Rotation + Reverse + Add Pages)"""
        try:
            stage2 = config.get("processing_sequence", {}).get("stage_2", {})
            operations = stage2.get("operations", {})

            # Helper: make destination path unique to avoid overwrites
            def _unique_path(dst_path: str) -> str:
                try:
                    if not os.path.exists(dst_path):
                        return dst_path
                    base_dir = os.path.dirname(dst_path)
                    base_name = os.path.basename(dst_path)
                    name, ext = os.path.splitext(base_name)
                    counter = 1
                    while True:
                        candidate = os.path.join(base_dir, f"{name}_{counter}{ext}")
                        if not os.path.exists(candidate):
                            return candidate
                        counter += 1
                except Exception:
                    return dst_path
            
            # Check if Stage 2 operations are enabled
            rotation_enabled = operations.get("rotation", {}).get("enabled", False)
            reverse_enabled = operations.get("reverse_ordering", {}).get("enabled", False)
            append_enabled = operations.get("add_blank_pages", {}).get("enabled", False)
            
            if not (rotation_enabled or reverse_enabled or append_enabled):
                # No Stage 2 ops: copy Stage 1 output to final folder
                try:
                    os.makedirs(final_output_folder, exist_ok=True)
                    if os.path.isdir(input_folder):
                        for file in os.listdir(input_folder):
                            if file.lower().endswith('.pdf'):
                                src = os.path.join(input_folder, file)
                                dst = _unique_path(os.path.join(final_output_folder, file))
                                import shutil
                                shutil.copy2(src, dst)
                    else:
                        # Single file path
                        import shutil
                        if os.path.isfile(input_folder):
                            dst = _unique_path(os.path.join(final_output_folder, os.path.basename(input_folder)))
                            shutil.copy2(input_folder, dst)
                    self.conv_progress.setVisible(False)
                    self.conv_progress.setMaximum(100)
                    self.start_stage1_btn.setEnabled(True)
                    QMessageBox.information(self, "Processing Complete", f"Stage 1 outputs saved to: {os.path.basename(final_output_folder)}")
                    self.status_label.setText(f"Saved to: {os.path.basename(final_output_folder)}")
                except Exception as e:
                    self.conv_progress.setVisible(False)
                    self.conv_progress.setMaximum(100)
                    self.start_stage1_btn.setEnabled(True)
                    QMessageBox.critical(self, "Save Failed", f"Failed to save to final folder: {e}")
                    self.status_label.setText(f"Error: {e}")
                return
            
            # Setup Stage 2 output directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            temp_folder_2 = os.path.join(script_dir, "TEMP_FOLDER_2")
            
            # Clean up existing files in output folder
            if os.path.exists(temp_folder_2):
                import shutil
                shutil.rmtree(temp_folder_2)
            os.makedirs(temp_folder_2, exist_ok=True)
            
            self.status_label.setText("Starting Stage 2 processing...")
            
            # Get files for Stage 2. If input_folder is Stage 1 output, ALWAYS prefer files under it
            if os.path.isdir(input_folder):
                stage2_files = []
                if include_files:
                    # Map by basename into the input_folder (TEMP_FOLDER_1)
                    for p in include_files:
                        candidate = os.path.join(input_folder, os.path.basename(p))
                        if os.path.isfile(candidate):
                            stage2_files.append(candidate)
                if not stage2_files:
                    # Fallback: scan directory for PDFs
                    for file in os.listdir(input_folder):
                        if file.lower().endswith('.pdf'):
                            stage2_files.append(os.path.join(input_folder, file))
            else:
                stage2_files = include_files
            
            if not stage2_files:
                QMessageBox.warning(self, "No Files", "No PDF files found for Stage 2 processing.")
                return
            
            # Start Stage 2 worker thread
            self.stage2_thread = QThread()
            self.stage2_worker = _Stage2ProcessingWorker(
                include_files=stage2_files,
                output_folder=temp_folder_2,
                config=config,
                final_output_folder=final_output_folder
            )
            self.stage2_worker.moveToThread(self.stage2_thread)
            
            self.stage2_thread.started.connect(self.stage2_worker.run)
            self.stage2_worker.finished.connect(self.stage2_thread.quit)
            self.stage2_worker.finished.connect(self.stage2_worker.deleteLater)
            self.stage2_thread.finished.connect(self.stage2_thread.deleteLater)
            self.stage2_worker.progress.connect(self._on_stage2_progress)
            self.stage2_worker.error.connect(self._on_stage2_error)
            self.stage2_worker.success.connect(self._on_stage2_success)
            
            try:
                self.stage2_thread.setPriority(QThread.LowestPriority)
            except Exception:
                pass
            self.stage2_thread.start()
            try:
                self.stop_stage_btn.setEnabled(True)
            except Exception:
                pass
            
        except Exception as e:
            QMessageBox.critical(self, "Stage 2 Error", f"Failed to start Stage 2 processing: {e}")
            self.start_stage1_btn.setEnabled(True)
            self.conv_progress.setVisible(False)

    def _on_stage2_progress(self, message: str):
        """Handle Stage 2 progress updates"""
        self.status_label.setText(message)

    def _stop_stage_processing(self):
        try:
            # Attempt to cancel stage1
            if hasattr(self, 'stage1_worker') and self.stage1_worker is not None:
                try:
                    self.stage1_worker.cancel()
                except Exception:
                    pass
            # Attempt to cancel stage2
            if hasattr(self, 'stage2_worker') and self.stage2_worker is not None:
                try:
                    self.stage2_worker.cancel()
                except Exception:
                    pass
            # Hide progress and disable stop
            self.conv_progress.setVisible(False)
            self.conv_progress.setMaximum(100)
            try:
                self.stop_stage_btn.setEnabled(False)
            except Exception:
                pass
            self.status_label.setText("Stopping...")
        except Exception:
            pass

    def _on_stage2_error(self, message: str):
        """Handle Stage 2 errors"""
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_stage1_btn.setEnabled(True)
        try:
            self.stop_stage_btn.setEnabled(False)
        except Exception:
            pass
        QMessageBox.critical(self, "Stage 2 Failed", message)
        self.status_label.setText(f"Error: {message}")

    def _on_stage2_success(self, output_folder: str):
        """Handle Stage 2 completion"""
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_stage1_btn.setEnabled(True)
        try:
            self.stop_stage_btn.setEnabled(False)
        except Exception:
            pass
        QMessageBox.information(self, "Processing Complete", f"Processing completed successfully!\nOutput saved to: {os.path.basename(output_folder)}")
        self.status_label.setText(f"Processing completed: {os.path.basename(output_folder)}")

    def _update_processing_config(self):
        """Update the processing configuration JSON file with current settings"""
        try:
            # Initialize config if not exists
            if not hasattr(self, 'rotation_config'):
                self.rotation_config = {"enabled": False}
            if not hasattr(self, 'reverse_config'):
                self.reverse_config = {"enabled": False}
            if not hasattr(self, 'append_config'):
                self.append_config = {"enabled": False}
            if not hasattr(self, 'scaling_config'):
                self.scaling_config = {"enabled": False}
            if not hasattr(self, 'margin_config'):
                self.margin_config = {"enabled": False}
            if not hasattr(self, 'dpi_config'):
                self.dpi_config = {"enabled": False}

            # Build processing configuration
            processing_config = {
                "processing_sequence": {
                    "stage_1": {
                        "name": "Page Processing (DPI → Scaling → Margins)",
                        "processing_type": "batch_threading",
                        "operations": {
                            "dpi_adjustment": {
                                "enabled": self.dpi_config.get("enabled", False),
                                "x_dpi": self.dpi_config.get("x_dpi", 300),
                                "y_dpi": self.dpi_config.get("y_dpi", 300)
                            },
                            "page_scaling": {
                                "enabled": self.scaling_config.get("enabled", False),
                                "target_width_mm": self.scaling_config.get("target_width_mm", 210),
                                "target_height_mm": self.scaling_config.get("target_height_mm", 297)
                            },
                            "pdf_margin_adjustment": {
                                "enabled": self.margin_config.get("enabled", False),
                                "top_margin": self.margin_config.get("top", 0),
                                "bottom_margin": self.margin_config.get("bottom", 0),
                                "left_margin": self.margin_config.get("left", 0),
                                "right_margin": self.margin_config.get("right", 0)
                            }
                        },
                        "output_folder": "TEMP_FOLDER_1"
                    },
                    "stage_2": {
                        "name": "Document Structure (Full PDF operations)",
                        "processing_type": "sequential_full_pdf",
                        "operations": {
                            "rotation": {
                                "enabled": self.rotation_config.get("enabled", False),
                                "angle": self.rotation_config.get("angle", 0)
                            },
                            "reverse_ordering": {
                                "enabled": self.reverse_config.get("enabled", False)
                            },
                            "add_blank_pages": {
                                "enabled": self.append_config.get("enabled", False),
                                "pages_to_append": self.append_config.get("pages", 1),
                                "mode": self.append_config.get("mode", 0),
                                "after_page": self.append_config.get("after_page", -1)
                            }
                        },
                        "output_folder": "FINAL_OUTPUT_FOLDER"
                    }
                },
                "execution_order": [
                    "stage_1",
                    "stage_2"
                ],
                "flow_description": "Input → Stage 1 (DPI → Scaling → Margins) → TEMP_1 → Stage 2 (Structure) → Final Output",
                "generated_at": str(Path().cwd()),
                "config_version": "1.0"
            }

            # Save to processing config file
            processing_config_path = self.config_dir / "processing_config.json"
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            with processing_config_path.open('w', encoding='utf-8') as f:
                json.dump(processing_config, f, indent=2)
                
            self.status_label.setText(f"Processing config updated: {processing_config_path}")
            
        except Exception as e:
            self.status_label.setText(f"Error updating processing config: {e}")
            print(f"Error updating processing config: {e}")

    def _apply_group_styling(self, enabled, group_type):
        """Apply faded styling to disabled feature groups"""
        try:
            # Map group type to stored reference
            group_map = {
                "rotate": getattr(self, 'rotate_group_box', None),
                "reverse": getattr(self, 'reverse_group_box', None),
                "append": getattr(self, 'append_group_box', None),
                "scaling": getattr(self, 'scaling_group_box', None),
                "margin": getattr(self, 'margin_group_box', None),
                "dpi": getattr(self, 'dpi_group_box', None),
                "color": getattr(self, 'color_group_box', None),
            }
            
            group_box = group_map.get(group_type)
            
            if group_box:
                if enabled:
                    # Feature is ENABLED - normal styling (remove background color)
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
                else:
                    # Feature is DISABLED - faded styling
                    group_box.setStyleSheet("""
                        QGroupBox {
                            font-weight: bold;
                            font-size: 12pt;
                            color: #6c757d;
                            border: 1px solid #dee2e6;
                            border-radius: 8px;
                            margin-top: 20px;
                            padding-top: 10px;
                            background-color: #f8f9fa;
                        }
                        QGroupBox::title {
                            subcontrol-origin: margin;
                            subcontrol-position: top left;
                            left: 0px;
                            padding: 0 8px;
                            background: transparent;
                            font-weight: bold;
                            font-size: 12pt;
                            color: #6c757d;
                        }
                    """)
        except Exception as e:
            print(f"Error in _apply_group_styling for {group_type}: {e}")

    def _exclude_pdf(self, full_path: str):
        try:
            self.excluded_paths.add(full_path)
            # Remove the corresponding item from the list view
            for row in range(self.folder_pdf_list.count()):
                item = self.folder_pdf_list.item(row)
                if item.data(Qt.UserRole) == full_path:
                    self.folder_pdf_list.takeItem(row)
                    break
            # Also drop label mapping
            if full_path in self.folder_item_labels:
                del self.folder_item_labels[full_path]
            # Update status
            self.status_label.setText(f"Excluded from processing: {os.path.basename(full_path)}")
        except Exception:
            pass

    def _open_config_folder(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            path = str(self.config_dir.resolve())
            if os.name == 'nt':
                os.startfile(path)
            elif os.name == 'posix' and "darwin" in os.sys.platform:
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open config folder: {e}")

    def _browse_output_global(self):
        try:
            folder = QFileDialog.getExistingDirectory(self, "Select Output Folder (Final PDFs)", os.getcwd())
            if folder:
                self.output_path_edit.setText(folder)
        except Exception:
            pass

    def _load_pdf_preview(self):
        """Load first page of the selected PDF into the graphics view."""
        try:
            self._set_preview_mode('regions')
            src = self.input_path_edit.text().strip()
            if not src:
                QMessageBox.warning(self, "No Input", "Select a PDF file or a folder containing PDFs.")
                return
            pdf_path = src
            if os.path.isdir(src):
                # Pick first PDF in folder
                pdfs = [f for f in os.listdir(src) if f.lower().endswith('.pdf')]
                if not pdfs:
                    QMessageBox.warning(self, "No PDFs", "The selected folder contains no PDF files.")
                    return
                pdf_path = os.path.join(src, pdfs[0])

            if not pdf_path.lower().endswith('.pdf') or not os.path.exists(pdf_path):
                QMessageBox.warning(self, "Invalid PDF", "Please select a valid PDF file.")
                return

            import fitz
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                doc.close()
                QMessageBox.warning(self, "Empty PDF", "The selected PDF has no pages.")
                return
            page = doc[0]
            from .render_utils import qimage_from_page, clamp_dpi
            xdpi = clamp_dpi(int(self.x_dpi_spin.value())) if hasattr(self, 'x_dpi_spin') else 300
            ydpi = clamp_dpi(int(self.y_dpi_spin.value())) if hasattr(self, 'y_dpi_spin') else xdpi
            qimg = qimage_from_page(page, xdpi, ydpi)
            self.page_pixmap = QPixmap.fromImage(qimg)
            self.graphics_scene.clear()
            self.page_pixmap_item = self.graphics_scene.addPixmap(self.page_pixmap)
            self.graphics_scene.setSceneRect(QRectF(self.page_pixmap.rect()))
            self.graphics_view.fitInView(self.graphics_scene.sceneRect(), Qt.KeepAspectRatio)
            self._redraw_regions()
            doc.close()
            self.status_label.setText(f"Loaded preview: {Path(pdf_path).name}")
            # Update preview file label
            self.preview_file_label.setText(f"Preview: {Path(pdf_path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Preview Error", f"Failed to load preview: {e}")
            self.status_label.setText("Preview error")

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

    def _style_enable_checkbox(self, checkbox):
        try:
            checkbox.setStyleSheet(
                """
                QCheckBox { color: #212529; }
                QCheckBox::indicator {
                    width: 16px; height: 16px;
                    border: 1px solid #ced4da; border-radius: 3px; background: #ffffff;
                }
                QCheckBox::indicator:checked {
                    background-color: #28a745; border-color: #28a745;
                }
                QCheckBox::indicator:unchecked {
                    background-color: #ffffff;
                }
                """
            )
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

    def _format_points_to_mm(self, size_points):
        try:
            w_pt, h_pt = size_points
            w_mm = round(w_pt * 25.4 / 72.0)
            h_mm = round(h_pt * 25.4 / 72.0)
            return f"{w_mm} × {h_mm} mm"
        except Exception:
            return "? × ? mm"

    def _get_optimal_workers(self) -> int:
        """Get optimal number of worker threads based on CPU and memory"""
        try:
            cpu_count = os.cpu_count() or 4
            reserve_for_gui = 1  # leave one core for the GUI thread
            max_threads_from_cpu = max(1, cpu_count - reserve_for_gui)

            if PSUTIL_AVAILABLE:
                available_gb = psutil.virtual_memory().available / (1024**3)
                memory_based = max(1, int(available_gb / 2))  # ~2GB per worker
                optimal = min(memory_based, max_threads_from_cpu, 12)  # cap lower to reduce contention
                print(f"[Performance] CPU cores: {cpu_count}, Avail RAM: {available_gb:.1f}GB, Workers: {optimal}")
            else:
                optimal = min(max_threads_from_cpu, 12)
                print(f"[Performance] CPU cores: {cpu_count}, Workers: {optimal}")

            return max(2, optimal)
        except Exception as e:
            print(f"[Performance] Error calculating optimal workers: {e}, using default 8")
            return 8

    def _get_optimal_batch_size(self, total_pages: int) -> int:
        """Get optimal batch size based on PDF size"""
        try:
            if total_pages <= 50:
                return total_pages  # Single batch for small PDFs
            elif total_pages <= 200:
                return 50
            elif total_pages <= 500:
                return 75
            else:
                return 100  # Larger batches for big PDFs
        except Exception:
            return 50  # Default fallback

    def _on_folder_selection_changed(self, row: int):
        try:
            item = self.folder_pdf_list.item(row) if row >= 0 else None
            total_pages = item.data(Qt.UserRole + 1) if item else None
            # Enable or disable the after-page selector depending on mode
            mode = self.append_mode_combo.currentIndex() if hasattr(self, 'append_mode_combo') else 0
            is_after = (mode == 1)
            self.append_after_label.setVisible(is_after)
            self.append_after_page_spin.setEnabled(is_after)
            if total_pages and isinstance(total_pages, int) and total_pages > 0:
                self.append_after_page_spin.setMaximum(total_pages)
            else:
                self.append_after_page_spin.setMaximum(99999)
        except Exception:
            pass

    def _on_append_mode_changed(self, index: int):
        try:
            is_after = (index == 1)
            self.append_after_label.setVisible(is_after)
            self.append_after_page_spin.setEnabled(is_after)
        except Exception:
            pass

    # --- Conversion Flow -----------------------------------------------------
    def _start_colour_conversion(self):
        try:
            # Save config before running
            self._save_config()
        except Exception:
            pass

        # Prefer Controls section inputs if provided
        input_path = ''
        output_path_override = ''
        try:
            if hasattr(self, 'cc_input_edit') and self.cc_input_edit.text().strip():
                input_path = self.cc_input_edit.text().strip()
        except Exception:
            pass
        if not input_path:
            # Fallback to main configuration input_path
            cfg_path = str(self.config_path)
            try:
                with self.config_path.open('r', encoding='utf-8') as f:
                    cfg = json.load(f)
                input_path = cfg.get('settings', {}).get('input_path', '').strip()
            except Exception as e:
                QMessageBox.critical(self, "Config Error", f"Could not read config: {e}")
                return

        # Force default DPI to 300x300 for color conversion
        x_dpi = 300
        y_dpi = 300

        # Use optimized defaults for better performance
        max_workers = self._get_optimal_workers()
        batch_size = 50  # Increased from 25 for better performance

        if not input_path:
            QMessageBox.warning(self, "Missing Input", "Please select an input folder or PDF file in Configuration.")
            return

        # Determine output path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        default_output = os.path.join(script_dir, "colored_output")
        try:
            if hasattr(self, 'cc_output_edit') and self.cc_output_edit.text().strip():
                output_path_override = self.cc_output_edit.text().strip()
        except Exception:
            pass
        final_output_dir = output_path_override if output_path_override else default_output

        # Disable controls and show progress (indeterminate)
        self.start_conversion_btn.setEnabled(False)
        self.show_converted_btn.setEnabled(False)
        self.conv_progress.setVisible(True)
        self.conv_progress.setMaximum(0)
        self.status_label.setText("Starting conversion…")

        # Start worker thread
        self.conv_thread = QThread()
        include_files = []
        try:
            # Prefer the Controls list selection if present
            if hasattr(self, 'cc_pdf_list') and os.path.isdir(input_path):
                for i in range(self.cc_pdf_list.count()):
                    it = self.cc_pdf_list.item(i)
                    if it:
                        p = it.data(Qt.UserRole)
                        if p and os.path.isfile(p):
                            include_files.append(p)
            elif os.path.isdir(input_path):
                for i in range(self.folder_pdf_list.count()):
                    it = self.folder_pdf_list.item(i)
                    p = it.data(Qt.UserRole)
                    if p and os.path.isfile(p):
                        include_files.append(p)
        except Exception:
            pass

        self.conv_worker = _ColourConversionWorker(
            input_path=input_path,
            output_path=final_output_dir,
            config_json=str(self.config_path),
            x_dpi=x_dpi,
            y_dpi=y_dpi,
            max_workers=max_workers,
            batch_size=batch_size,
            include_files=include_files if include_files else None
        )
        self.conv_worker.moveToThread(self.conv_thread)

        self.conv_thread.started.connect(self.conv_worker.run)
        self.conv_worker.finished.connect(self.conv_thread.quit)
        self.conv_worker.finished.connect(self.conv_worker.deleteLater)
        self.conv_thread.finished.connect(self.conv_thread.deleteLater)
        self.conv_worker.progress.connect(self._on_conv_progress)
        self.conv_worker.error.connect(self._on_conv_error)
        self.conv_worker.success.connect(self._on_conv_success)

        self.conv_thread.start()

    def _on_conv_progress(self, message: str):
        self.status_label.setText(message)

    def _on_conv_error(self, message: str):
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_conversion_btn.setEnabled(True)
        self.show_converted_btn.setEnabled(True)
        QMessageBox.critical(self, "Conversion Failed", message)
        self.status_label.setText(f"Error: {message}")

    def _on_conv_success(self, last_output_path: str):
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_conversion_btn.setEnabled(True)
        self.show_converted_btn.setEnabled(True)
        QMessageBox.information(self, "Conversion Complete", "PDF conversion completed successfully!")
        # Auto-open preview chooser
        self._select_converted_pdf(prefill_path=last_output_path)

    def _start_pdf_scaling(self):
        try:
            # Save config before running
            self._save_config()
        except Exception:
            pass

        # Read config for run
        cfg_path = str(self.config_path)
        try:
            with self.config_path.open('r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Config Error", f"Could not read config: {e}")
            return

        input_path = cfg.get('settings', {}).get('input_path', '').strip()
        dpi = int(cfg.get('settings', {}).get('dpi', 300))
        # Use optimized defaults for better performance
        max_workers = self._get_optimal_workers()
        batch_size = 50  # Increased from 25 for better performance
        scaling_percent = int(self.scaling_spin.value())

        if not input_path:
            QMessageBox.warning(self, "Missing Input", "Please select an input folder or PDF file in Configuration.")
            return

        if scaling_percent == 0:
            QMessageBox.warning(self, "Invalid Scaling", "Scaling percentage cannot be 0%")
            return

        # Determine output path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        default_output = os.path.join(script_dir, "scaled_output")

        # Disable controls and show progress (indeterminate)
        self.start_scaling_btn.setEnabled(False)
        self.start_conversion_btn.setEnabled(False)
        self.show_converted_btn.setEnabled(False)
        self.conv_progress.setVisible(True)
        self.conv_progress.setMaximum(0)
        self.status_label.setText("Starting PDF scaling...")

        # Start worker thread
        self.scaling_thread = QThread()
        include_files = []
        try:
            if os.path.isdir(input_path):
                excluded = getattr(self, 'excluded_paths', set())
                for i in range(self.folder_pdf_list.count()):
                    it = self.folder_pdf_list.item(i)
                    p = it.data(Qt.UserRole)
                    if p and os.path.isfile(p) and p not in excluded:
                        include_files.append(p)
        except Exception:
            pass

        self.scaling_worker = _PDFScalingWorker(
            input_path=input_path,
            output_path=default_output,
            scaling_percent=scaling_percent,
            dpi=dpi,
            max_workers=max_workers,
            batch_size=batch_size,
            include_files=include_files if include_files else None
        )
        self.scaling_worker.moveToThread(self.scaling_thread)

        self.scaling_thread.started.connect(self.scaling_worker.run)
        self.scaling_worker.finished.connect(self.scaling_thread.quit)
        self.scaling_worker.finished.connect(self.scaling_worker.deleteLater)
        self.scaling_thread.finished.connect(self.scaling_thread.deleteLater)
        self.scaling_worker.progress.connect(self._on_scaling_progress)
        self.scaling_worker.error.connect(self._on_scaling_error)
        self.scaling_worker.success.connect(self._on_scaling_success)

        self.scaling_thread.start()

    def _on_scaling_progress(self, message: str):
        self.status_label.setText(message)

    def _on_scaling_error(self, message: str):
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_scaling_btn.setEnabled(True)
        self.start_conversion_btn.setEnabled(True)
        self.show_converted_btn.setEnabled(True)
        QMessageBox.critical(self, "Scaling Failed", message)
        self.status_label.setText(f"Error: {message}")

    def _on_scaling_success(self, last_output_path: str):
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_scaling_btn.setEnabled(True)
        self.start_conversion_btn.setEnabled(True)
        self.show_converted_btn.setEnabled(True)
        QMessageBox.information(self, "Scaling Complete", f"PDF scaling completed successfully!\nScaled PDFs saved to: {os.path.basename(last_output_path)}")
        self.status_label.setText(f"Scaling completed: {os.path.basename(last_output_path)}")

    def _start_pdf_margin_adjustment(self):
        try:
            # Save config before running
            self._save_config()
        except Exception:
            pass

        # Read config for run
        cfg_path = str(self.config_path)
        try:
            with self.config_path.open('r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Config Error", f"Could not read config: {e}")
            return

        input_path = cfg.get('settings', {}).get('input_path', '').strip()
        dpi = int(cfg.get('settings', {}).get('dpi', 300))
        # Use optimized defaults for better performance
        max_workers = self._get_optimal_workers()
        batch_size = 50  # Increased from 25 for better performance

        if not input_path:
            QMessageBox.warning(self, "Missing Input", "Please select an input folder or PDF file in Configuration.")
            return

        # Get margin values
        top_margin = float(self.top_margin_spin.value())
        bottom_margin = float(self.bottom_margin_spin.value())
        left_margin = float(self.left_margin_spin.value())
        right_margin = float(self.right_margin_spin.value())

        # Check if any margin adjustment is needed
        if abs(top_margin) < 1e-9 and abs(bottom_margin) < 1e-9 and abs(left_margin) < 1e-9 and abs(right_margin) < 1e-9:
            QMessageBox.warning(self, "No Margin Adjustment", "Please set at least one margin value (non-zero)")
            return

        # Determine output path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        default_output = os.path.join(script_dir, "margin_adjusted_output")

        # Disable controls and show progress (indeterminate)
        self.start_margin_btn.setEnabled(False)
        self.start_conversion_btn.setEnabled(False)
        self.start_scaling_btn.setEnabled(False)
        self.show_converted_btn.setEnabled(False)
        self.conv_progress.setVisible(True)
        self.conv_progress.setMaximum(0)
        self.status_label.setText("Starting PDF margin adjustment...")

        # Start worker thread
        self.margin_thread = QThread()
        include_files = []
        try:
            if os.path.isdir(input_path):
                excluded = getattr(self, 'excluded_paths', set())
                for i in range(self.folder_pdf_list.count()):
                    it = self.folder_pdf_list.item(i)
                    p = it.data(Qt.UserRole)
                    if p and os.path.isfile(p) and p not in excluded:
                        include_files.append(p)
        except Exception:
            pass

        self.margin_worker = _PDFMarginWorker(
            input_path=input_path,
            output_path=default_output,
            top_margin=top_margin,
            bottom_margin=bottom_margin,
            left_margin=left_margin,
            right_margin=right_margin,
            dpi=dpi,
            max_workers=max_workers,
            batch_size=batch_size,
            include_files=include_files if include_files else None
        )
        self.margin_worker.moveToThread(self.margin_thread)

        self.margin_thread.started.connect(self.margin_worker.run)
        self.margin_worker.finished.connect(self.margin_thread.quit)
        self.margin_worker.finished.connect(self.margin_worker.deleteLater)
        self.margin_thread.finished.connect(self.margin_thread.deleteLater)
        self.margin_worker.progress.connect(self._on_margin_progress)
        self.margin_worker.error.connect(self._on_margin_error)
        self.margin_worker.success.connect(self._on_margin_success)

        self.margin_thread.start()

    def _on_margin_progress(self, message: str):
        self.status_label.setText(message)

    def _on_margin_error(self, message: str):
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_margin_btn.setEnabled(True)
        self.start_conversion_btn.setEnabled(True)
        self.start_scaling_btn.setEnabled(True)
        self.show_converted_btn.setEnabled(True)
        QMessageBox.critical(self, "Margin Adjustment Failed", message)
        self.status_label.setText(f"Error: {message}")

    def _on_margin_success(self, last_output_path: str):
        self.conv_progress.setVisible(False)
        self.conv_progress.setMaximum(100)
        self.start_margin_btn.setEnabled(True)
        self.start_conversion_btn.setEnabled(True)
        self.start_scaling_btn.setEnabled(True)
        self.show_converted_btn.setEnabled(True)
        QMessageBox.information(self, "Margin Adjustment Complete", f"PDF margin adjustment completed successfully!\nAdjusted PDFs saved to: {os.path.basename(last_output_path)}")
        self.status_label.setText(f"Margin adjustment completed: {os.path.basename(last_output_path)}")

    def _start_pdf_rotation(self):
        try:
            # Read input
            src = self.input_path_edit.text().strip()
            if not src or not os.path.isdir(src):
                QMessageBox.warning(self, "No Folder", "Please select an input folder containing PDFs.")
                return
            # Angle chosen (radio group ensures a single selection)
            angle_id = self.rot_group.checkedId() if hasattr(self, 'rot_group') else 0
            angles = [angle_id]
            if angle_id == -1:
                QMessageBox.warning(self, "Rotation", "Please select at least one angle.")
                return
            # Determine include files (respect exclusions)
            include_files = []
            for i in range(self.folder_pdf_list.count()):
                it = self.folder_pdf_list.item(i)
                p = it.data(Qt.UserRole)
                if p and os.path.isfile(p):
                    include_files.append(p)

            # Output dir
            script_dir = os.path.dirname(os.path.abspath(__file__))
            out_dir = os.path.join(script_dir, "rotated_output")

            # Disable UI bits
            self.start_rotation_btn.setEnabled(False)
            self.start_conversion_btn.setEnabled(False)
            self.start_scaling_btn.setEnabled(False)
            self.start_margin_btn.setEnabled(False)
            self.show_converted_btn.setEnabled(False)
            self.conv_progress.setVisible(True)
            self.conv_progress.setMaximum(0)
            self.status_label.setText("Starting rotation...")

            # Start worker
            self.rotate_thread = QThread()
            self.rotate_worker = _PDFRotateWorker(folder_path=src, output_path=out_dir, angles=angles, include_files=include_files)
            self.rotate_worker.moveToThread(self.rotate_thread)
            self.rotate_thread.started.connect(self.rotate_worker.run)
            self.rotate_worker.finished.connect(self.rotate_thread.quit)
            self.rotate_worker.finished.connect(self.rotate_worker.deleteLater)
            self.rotate_thread.finished.connect(self.rotate_thread.deleteLater)
            self.rotate_worker.progress.connect(self._on_scaling_progress)
            self.rotate_worker.error.connect(self._on_scaling_error)
            self.rotate_worker.success.connect(self._on_scaling_success)
            self.rotate_thread.start()
        except Exception:
            pass

    def _start_pdf_reverse(self):
        try:
            src = self.input_path_edit.text().strip()
            if not src or not os.path.isdir(src):
                QMessageBox.warning(self, "No Folder", "Please select an input folder containing PDFs.")
                return
            if hasattr(self, 'reverse_enabled_cb') and not self.reverse_enabled_cb.isChecked():
                QMessageBox.information(self, "Reverse Ordering", "Enable the checkbox to run reverse ordering.")
                return
            include_files = []
            for i in range(self.folder_pdf_list.count()):
                it = self.folder_pdf_list.item(i)
                p = it.data(Qt.UserRole)
                if p and os.path.isfile(p):
                    include_files.append(p)
            script_dir = os.path.dirname(os.path.abspath(__file__))
            out_dir = os.path.join(script_dir, "reversed_output")

            self.start_reverse_btn.setEnabled(False)
            self.start_rotation_btn.setEnabled(False)
            self.start_conversion_btn.setEnabled(False)
            self.start_scaling_btn.setEnabled(False)
            self.start_margin_btn.setEnabled(False)
            self.show_converted_btn.setEnabled(False)
            self.conv_progress.setVisible(True)
            self.conv_progress.setMaximum(0)
            self.status_label.setText("Starting reverse ordering...")

            self.reverse_thread = QThread()
            self.reverse_worker = _PDFReverseWorker(folder_path=src, output_path=out_dir, include_files=include_files)
            self.reverse_worker.moveToThread(self.reverse_thread)
            self.reverse_thread.started.connect(self.reverse_worker.run)
            self.reverse_worker.finished.connect(self.reverse_thread.quit)
            self.reverse_worker.finished.connect(self.reverse_worker.deleteLater)
            self.reverse_thread.finished.connect(self.reverse_thread.deleteLater)
            self.reverse_worker.progress.connect(self._on_scaling_progress)
            self.reverse_worker.error.connect(self._on_scaling_error)
            self.reverse_worker.success.connect(self._on_scaling_success)
            self.reverse_thread.start()
        except Exception:
            pass

    def _select_converted_pdf(self, prefill_path: str = ""):
        try:
            if prefill_path and os.path.exists(prefill_path):
                start_dir = os.path.dirname(prefill_path)
            else:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                start_dir = os.path.join(script_dir, "colored_output")
            pdf_path, _ = QFileDialog.getOpenFileName(self, "Select Converted PDF", start_dir, "PDF Files (*.pdf)")
            if not pdf_path:
                return
            self._open_converted_pdf(pdf_path)
        except Exception as e:
            QMessageBox.warning(self, "Preview", f"Could not open converted PDF: {e}")

    def _open_converted_pdf(self, pdf_path: str):
        try:
            import fitz
            if self.converted_doc is not None:
                try:
                    self.converted_doc.close()
                except Exception:
                    pass
            self.converted_doc = fitz.open(pdf_path)
            self.converted_pdf_path = pdf_path
            self.converted_total_pages = len(self.converted_doc)
            self.converted_current_page = 0
            # Update UI controls
            self._set_preview_mode('converted')
            self.preview_file_label.setText(f"Converted PDF: {Path(pdf_path).name}")
            self.page_spin.setEnabled(True)
            self.page_spin.setRange(1, max(1, self.converted_total_pages))
            self.prev_page_btn.setEnabled(self.converted_total_pages > 1)
            self.next_page_btn.setEnabled(self.converted_total_pages > 1)
            # Render first page
            self._render_converted_page(0)
        except Exception as e:
            QMessageBox.critical(self, "Converted Preview", f"Failed to load PDF: {e}")

    def _render_converted_page(self, page_index: int):
        try:
            if not self.converted_doc or page_index < 0 or page_index >= self.converted_total_pages:
                return
            page = self.converted_doc[page_index]
            from .render_utils import qimage_from_page, clamp_dpi
            xdpi = clamp_dpi(int(self.x_dpi_spin.value())) if hasattr(self, 'x_dpi_spin') else 300
            ydpi = clamp_dpi(int(self.y_dpi_spin.value())) if hasattr(self, 'y_dpi_spin') else xdpi
            qimg = qimage_from_page(page, xdpi, ydpi)
            self.page_pixmap = QPixmap.fromImage(qimg)
            self.graphics_scene.clear()
            self.page_pixmap_item = self.graphics_scene.addPixmap(self.page_pixmap)
            self.graphics_scene.setSceneRect(QRectF(self.page_pixmap.rect()))
            self.graphics_view.fitInView(self.graphics_scene.sceneRect(), Qt.KeepAspectRatio)
            self.converted_current_page = page_index
            self.page_spin.blockSignals(True)
            self.page_spin.setValue(page_index + 1)
            self.page_spin.blockSignals(False)
        except Exception as e:
            QMessageBox.warning(self, "Converted Preview", f"Failed to render page: {e}")

    def _on_page_spin_changed(self, value: int):
        # value is 1-based
        self._goto_converted_page(value)

    def _goto_converted_page(self, one_based_target: int):
        try:
            if not self.converted_doc:
                return
            target_index = max(0, min(self.converted_total_pages - 1, one_based_target - 1))
            self._render_converted_page(target_index)
        except Exception:
            pass

    def _set_preview_mode(self, mode: str):
        self._view_mode = mode
        # In converted mode we do not draw editable region overlays
        # Graphics scene is reset by each renderer

    # --- Config I/O ----------------------------------------------------------
    def _current_config(self) -> dict:
        # Export regions without transient graphics items
        export_regions = []
        for idx, region in enumerate(self.regions, start=1):
            export_regions.append({
                "name": region.get("name", f"Region_{idx}"),
                "coordinates": list(region.get("coordinates", [0, 0, 0, 0])),
                "cmyk": list(region.get("cmyk", [100, 0, 0, 0])),
                "priority": idx
            })

        return {
            "settings": {
                "input_path": self.input_path_edit.text().strip(),
                "x_dpi": int(self.x_dpi_spin.value()) if hasattr(self, 'x_dpi_spin') else 300,
                "y_dpi": int(self.y_dpi_spin.value()) if hasattr(self, 'y_dpi_spin') else 300,
            },
            "regions": export_regions
        }

    def _save_config(self):
        try:
            cfg = self._current_config()

            # Basic validation
            input_path = cfg["settings"].get("input_path", "")
            if not input_path:
                QMessageBox.warning(self, "Missing Input", "Please select an input folder or PDF file.")
                return

            # Ensure directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)

            # Write JSON
            with self.config_path.open('w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)

            self.status_label.setText(f"Saved configuration → {self.config_path}")
            QMessageBox.information(self, "Configuration Saved",
                                    f"Configuration saved to:\n{self.config_path}")
        except Exception as e:
            self.status_label.setText("Error saving configuration")
            QMessageBox.critical(self, "Save Error", f"Failed to save config: {e}")

    def _load_config_if_present(self):
        try:
            if not self.config_path.exists():
                # Nothing to load; keep defaults
                self.status_label.setText("No existing config found. Defaults loaded.")
                return

            with self.config_path.open('r', encoding='utf-8') as f:
                data = json.load(f)

            settings = data.get("settings", {})
            # Do not prefill the input folder path; keep it blank by default
            self.input_path_edit.setText("")
            legacy_dpi = int(settings.get("dpi", 300))
            try:
                self.x_dpi_spin.setValue(int(settings.get("x_dpi", legacy_dpi)))
                self.y_dpi_spin.setValue(int(settings.get("y_dpi", legacy_dpi)))
            except Exception:
                pass
            # max_workers and batch_size inputs removed; keep internal defaults

            # Load regions
            self._clear_regions(confirm=False)
            for region in data.get("regions", []):
                self._add_region(region.get("coordinates", [0, 0, 0, 0]),
                                 region.get("cmyk", [100, 0, 0, 0]),
                                 name=region.get("name"))

            self.status_label.setText(f"Loaded configuration from {self.config_path}")
        except Exception as e:
            self.status_label.setText("Error loading configuration")
            QMessageBox.warning(self, "Load Config",
                                f"Failed to load existing config: {e}")

    # --- Regions / Drawing ---------------------------------------------------
    def _make_cmyk_slider(self, label_text):
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(0 if label_text == "Black:" else (100 if label_text == "Cyan:" else 0))
        slider.valueChanged.connect(self._update_color_preview)
        
        # Add input field for direct value entry
        value_input = QSpinBox()
        value_input.setRange(0, 100)
        value_input.setValue(slider.value())
        value_input.setMaximumWidth(60)
        
        # Connect slider to input
        slider.valueChanged.connect(value_input.setValue)
        # Connect input to slider
        value_input.valueChanged.connect(slider.setValue)
        # Connect both to color preview
        value_input.valueChanged.connect(self._update_color_preview)
        
        row.addWidget(slider, 1)
        row.addWidget(value_input)
        return row, slider, value_input

    def _update_color_preview(self):
        c = self.c_slider[1].value()
        m = self.m_slider[1].value()
        y = self.y_slider[1].value()
        k = self.k_slider[1].value()
        r = int(255 * (1 - c/100) * (1 - k/100))
        g = int(255 * (1 - m/100) * (1 - k/100))
        b = int(255 * (1 - y/100) * (1 - k/100))
        self.color_preview.setStyleSheet(f"background: rgb({r},{g},{b}); border:1px solid #ced4da; border-radius:3px;")

    def _current_cmyk(self):
        return [
            int(self.c_slider[1].value()),
            int(self.m_slider[1].value()),
            int(self.y_slider[1].value()),
            int(self.k_slider[1].value()),
        ]

    def begin_rectangle(self, scene_pos: QPointF):
        if self.page_pixmap is None:
            return
        self._drawing = True
        self._start_pos = scene_pos
        if self._temp_rect_item is not None:
            try:
                self.graphics_scene.removeItem(self._temp_rect_item)
            except Exception:
                pass
            self._temp_rect_item = None

    def update_rectangle(self, scene_pos: QPointF):
        if not self._drawing or self.page_pixmap is None:
            return
        rect = QRectF(self._start_pos, scene_pos).normalized()
        # Clamp to pixmap bounds
        bounds = QRectF(self.page_pixmap.rect())
        rect = rect.intersected(bounds)
        if self._temp_rect_item is None:
            self._temp_rect_item = QGraphicsRectItem(rect)
            self._temp_rect_item.setZValue(10)
            pen = QPen(QColor(255, 0, 0), 2)
            self._temp_rect_item.setPen(pen)
            self._temp_rect_item.setBrush(QBrush(QColor(255, 0, 0, 50)))
            self.graphics_scene.addItem(self._temp_rect_item)
        else:
            self._temp_rect_item.setRect(rect)

    def end_rectangle(self, scene_pos: QPointF):
        if not self._drawing or self.page_pixmap is None:
            return
        self._drawing = False
        if self._temp_rect_item is None:
            return
        rect = self._temp_rect_item.rect().normalized()
        try:
            self.graphics_scene.removeItem(self._temp_rect_item)
        except Exception:
            pass
        self._temp_rect_item = None

        if rect.width() < 5 or rect.height() < 5:
            return

        # Convert to normalized (0-1) coords based on pixmap size
        w = float(self.page_pixmap.width())
        h = float(self.page_pixmap.height())
        x1 = max(0.0, min(1.0, rect.left() / w))
        y1 = max(0.0, min(1.0, rect.top() / h))
        x2 = max(0.0, min(1.0, rect.right() / w))
        y2 = max(0.0, min(1.0, rect.bottom() / h))

        self._add_region([round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3)], self._current_cmyk())

    def _add_region(self, norm_coords, cmyk, name=None):
        if self.page_pixmap is None:
            # Store without graphics; will draw on preview load
            pass
        if name is None:
            name = f"Region_{len(self.regions) + 1}"

        region = {
            "name": name,
            "coordinates": list(norm_coords),
            "cmyk": list(cmyk),
            "priority": len(self.regions) + 1,
            "items": {}
        }
        self.regions.append(region)
        self._append_region_list_item(region)
        self._draw_region(region)

    def _append_region_list_item(self, region):
        c, m, y, k = region['cmyk']
        item = QListWidgetItem(f"{region['name']} - C:{c} M:{m} Y:{y} K:{k}")
        self.regions_list.addItem(item)

    def _draw_region(self, region):
        if self.page_pixmap is None:
            return
        w = float(self.page_pixmap.width())
        h = float(self.page_pixmap.height())
        x1, y1, x2, y2 = region['coordinates']
        rect = QRectF(x1 * w, y1 * h, (x2 - x1) * w, (y2 - y1) * h)
        c, m, y, k = region['cmyk']
        r = int(255 * (1 - c/100) * (1 - k/100))
        g = int(255 * (1 - m/100) * (1 - k/100))
        b = int(255 * (1 - y/100) * (1 - k/100))
        pen = QPen(QColor(r, g, b), 2)
        brush = QBrush(QColor(r, g, b, 60))
        rect_item = QGraphicsRectItem(rect)
        rect_item.setPen(pen)
        rect_item.setBrush(brush)
        rect_item.setZValue(5)
        self.graphics_scene.addItem(rect_item)
        region['items']['rect'] = rect_item

    def _redraw_regions(self):
        for region in self.regions:
            self._draw_region(region)

    def _on_region_selected(self, index):
        if index < 0 or index >= len(self.regions):
            return
        region = self.regions[index]
        c, m, y, k = region['cmyk']
        self.c_slider[1].setValue(c)
        self.m_slider[1].setValue(m)
        self.y_slider[1].setValue(y)
        self.k_slider[1].setValue(k)
        self._update_color_preview()

    def _delete_region(self):
        idx = self.regions_list.currentRow()
        if idx < 0 or idx >= len(self.regions):
            return
        region = self.regions.pop(idx)
        # remove graphics
        if region.get('items', {}).get('rect') is not None:
            try:
                self.graphics_scene.removeItem(region['items']['rect'])
            except Exception:
                pass
        self.regions_list.takeItem(idx)
        # reassign priorities
        for i, r in enumerate(self.regions, start=1):
            r['priority'] = i

    def _clear_regions(self, confirm=True):
        if confirm:
            res = QMessageBox.question(self, "Clear Regions", "Clear all regions?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if res != QMessageBox.Yes:
                return
        for region in self.regions:
            if region.get('items', {}).get('rect') is not None:
                try:
                    self.graphics_scene.removeItem(region['items']['rect'])
                except Exception:
                    pass
        self.regions.clear()
        self.regions_list.clear()


class _RegionGraphicsView(QGraphicsView):
    """Graphics view handling mouse to draw rectangles in scene coordinates."""
    def __init__(self, owner: PDFColourConversionSection):
        super().__init__()
        self.owner = owner
        self.setDragMode(QGraphicsView.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self.owner.begin_rectangle(scene_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.owner._drawing:
            scene_pos = self.mapToScene(event.pos())
            self.owner.update_rectangle(scene_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.owner._drawing and self.owner._view_mode == 'regions':
            scene_pos = self.mapToScene(event.pos())
            self.owner.end_rectangle(scene_pos)
        super().mouseReleaseEvent(event)


# --- Background Worker -------------------------------------------------------
class _ColourConversionWorker(QObject):
    finished = Signal()
    error = Signal(str)
    progress = Signal(str)
    success = Signal(str)  # last output path (folder or file)

    def __init__(self, input_path: str, output_path: str, config_json: str, x_dpi: int, y_dpi: int, max_workers: int, batch_size: int, include_files=None):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.config_json = config_json
        self.x_dpi = x_dpi
        self.y_dpi = y_dpi
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.include_files = include_files or None

    def run(self):
        try:
            self.progress.emit("Preparing conversion…")
            # Import here to avoid GUI start-up cost
            from pages.PDF_colour_conversion.pdf_colour_change import process_single_or_folder
            # Ensure output directory exists if folder mode
            last_output = self.output_path
            process_single_or_folder(
                input_path=self.input_path,
                output_path=self.output_path,
                config_json=self.config_json,
                x_dpi=self.x_dpi,
                y_dpi=self.y_dpi,
                max_workers=self.max_workers,
                batch_size=self.batch_size
            )
            self.progress.emit("Conversion completed")
            self.success.emit(last_output)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class _PDFScalingWorker(QObject):
    """
    Worker for scaling PDFs in background thread.
    """
    finished = Signal()
    error = Signal(str)
    progress = Signal(str)
    success = Signal(str)  # output folder path

    def __init__(self, input_path: str, output_path: str, scaling_percent: int, dpi: int, max_workers: int, batch_size: int, include_files=None):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.scaling_percent = scaling_percent
        self.dpi = dpi
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.include_files = include_files or None

    def run(self):
        try:
            self.progress.emit("Preparing PDF scaling...")
            
            # Import here to avoid GUI start-up cost
            from pages.PDF_colour_conversion.pdf_scaling import process_single_or_folder_scaling
            
            # Ensure output directory exists
            os.makedirs(self.output_path, exist_ok=True)
            
            # Process PDFs with scaling
            process_single_or_folder_scaling(
                input_path=self.input_path,
                output_path=self.output_path,
                scaling_percent=self.scaling_percent,
                dpi=self.dpi,
                max_workers=self.max_workers,
                batch_size=self.batch_size,
                include_files=self.include_files
            )
            
            self.progress.emit("PDF scaling completed")
            self.success.emit(self.output_path)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class _PDFMarginWorker(QObject):
    """
    Worker for adjusting PDF margins in background thread.
    """
    finished = Signal()
    error = Signal(str)
    progress = Signal(str)
    success = Signal(str)  # output folder path

    def __init__(self, input_path: str, output_path: str, top_margin: int, bottom_margin: int, 
                 left_margin: int, right_margin: int, dpi: int, max_workers: int, batch_size: int, include_files=None):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.top_margin = top_margin
        self.bottom_margin = bottom_margin
        self.left_margin = left_margin
        self.right_margin = right_margin
        self.dpi = dpi
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.include_files = include_files or None

    def run(self):
        try:
            self.progress.emit("Preparing PDF margin adjustment...")
            
            # Import here to avoid GUI start-up cost
            from pages.PDF_colour_conversion.pdf_margin_adjustment import process_single_or_folder_margin_adjustment
            
            # Ensure output directory exists
            os.makedirs(self.output_path, exist_ok=True)
            
            # Process PDFs with margin adjustment
            process_single_or_folder_margin_adjustment(
                input_path=self.input_path,
                output_path=self.output_path,
                top_margin=self.top_margin,
                bottom_margin=self.bottom_margin,
                left_margin=self.left_margin,
                right_margin=self.right_margin,
                dpi=self.dpi,
                max_workers=self.max_workers,
                batch_size=self.batch_size,
                include_files=self.include_files
            )
            
            self.progress.emit("PDF margin adjustment completed")
            self.success.emit(self.output_path)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class _PDFRotateWorker(QObject):
    finished = Signal()
    error = Signal(str)
    progress = Signal(str)
    success = Signal(str)

    def __init__(self, folder_path: str, output_path: str, angles, include_files=None):
        super().__init__()
        self.folder_path = folder_path
        self.output_path = output_path
        self.angles = angles
        self.include_files = include_files or None

    def run(self):
        try:
            self.progress.emit("Preparing PDF rotation...")
            try:
                from .pdf_rotate_pages import rotate_folder
            except Exception:
                from pages.PDF_colour_conversion.pdf_rotate_pages import rotate_folder
            os.makedirs(self.output_path, exist_ok=True)
            last = rotate_folder(
                input_path=self.folder_path,
                output_path=self.output_path,
                angles=self.angles,
                include_files=self.include_files
            )
            self.progress.emit("PDF rotation completed")
            self.success.emit(last)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class _PDFReverseWorker(QObject):
    finished = Signal()
    error = Signal(str)
    progress = Signal(str)
    success = Signal(str)

    def __init__(self, folder_path: str, output_path: str, include_files=None):
        super().__init__()
        self.folder_path = folder_path
        self.output_path = output_path
        self.include_files = include_files or None

    def run(self):
        try:
            self.progress.emit("Preparing reverse ordering...")
            try:
                from .pdf_reverse_pages import reverse_folder
            except Exception:
                from pages.PDF_colour_conversion.pdf_reverse_pages import reverse_folder
            os.makedirs(self.output_path, exist_ok=True)
            last = reverse_folder(
                input_path=self.folder_path,
                output_path=self.output_path,
                include_files=self.include_files
            )
            self.progress.emit("Reverse ordering completed")
            self.success.emit(last)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

class _PDFAppendBlankWorker(QObject):
    finished = Signal()
    error = Signal(str)
    success = Signal(str)
    progress = Signal(str)

    def __init__(self, pdf_path: str, output_dir: str, pages_to_append: int, mode: int = 0, after_page: int = -1):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.pages_to_append = pages_to_append
        # mode: 0=end, 1=after specific page, 2=alternate after each page
        self.mode = mode
        self.after_page = after_page

    def run(self):
        try:
            self.progress.emit("Preparing to append blank pages...")
            import fitz
            os.makedirs(self.output_dir, exist_ok=True)
            src = fitz.open(self.pdf_path)
            if len(src) == 0:
                src.close()
                raise Exception("Source PDF has no pages")
            # Read size from last page
            last = src[-1]
            width = last.rect.width
            height = last.rect.height
            # Create destination doc by copying/constructing per mode
            dst = fitz.open()
            if self.mode == 0:
                # At end
                dst.insert_pdf(src)
                for i in range(self.pages_to_append):
                    dst.new_page(width=width, height=height)
                name_suffix = f"with_{self.pages_to_append}_blank"
            elif self.mode == 1:
                # After a specific page number (1-based). If more than one to append, insert consecutively after that page
                insert_after = max(1, min(self.after_page if self.after_page > 0 else 1, len(src)))
                # Copy pages up to insert_after
                for i in range(len(src)):
                    dst.insert_pdf(src, from_page=i, to_page=i)
                    if (i + 1) == insert_after:
                        for _ in range(self.pages_to_append):
                            dst.new_page(width=width, height=height)
                name_suffix = f"after_{insert_after}_with_{self.pages_to_append}_blank"
            else:
                # Alternate after every page: after each original page, insert N blanks
                for i in range(len(src)):
                    dst.insert_pdf(src, from_page=i, to_page=i)
                    for _ in range(self.pages_to_append):
                        dst.new_page(width=width, height=height)
                name_suffix = f"alternate_each_with_{self.pages_to_append}_blank"
            # Save output
            base = os.path.basename(self.pdf_path)
            name, _ = os.path.splitext(base)
            out_path = os.path.join(self.output_dir, f"{name}_{name_suffix}.pdf")
            dst.save(out_path)
            dst.close()
            src.close()
            self.progress.emit("Blank pages appended")
            self.success.emit(out_path)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class _PDFDimensionCheckWorker(QObject):
    finished = Signal()
    error = Signal(str)
    success = Signal(dict)  # payload with results

    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = folder_path

    def run(self):
        try:
            try:
                # Prefer sibling import path when used in-app
                from .pdf_page_dimension_checker import (
                    check_folder_pdf_dimensions, format_points_to_mm,
                )
            except Exception:
                from pages.PDF_colour_conversion.pdf_page_dimension_checker import (
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


class _Stage1ProcessingWorker(QObject):
    """Worker for Stage 1 processing (DPI, Scaling, Margin) with batch/threading"""
    finished = Signal()
    error = Signal(str)
    progress = Signal(str)
    success = Signal(str)

    def __init__(self, include_files: list, output_folder: str, config: dict):
        super().__init__()
        self.include_files = include_files
        self.output_folder = output_folder
        self.config = config
        self.batch_size = 50  # Default batch size (will be optimized per PDF)
        self.max_workers = self._get_optimal_workers()
        self._cancelled = False

    def _get_optimal_workers(self) -> int:
        """Get optimal number of worker threads based on CPU and memory"""
        try:
            cpu_count = os.cpu_count() or 4
            
            if PSUTIL_AVAILABLE:
                # Memory-based threading (1 thread per 2GB RAM, max 2x CPU cores)
                available_gb = psutil.virtual_memory().available / (1024**3)
                memory_based = int(available_gb / 2)
                cpu_based = cpu_count * 2
                optimal = min(memory_based, cpu_based, 16)  # Cap at 16
                print(f"[Stage 1 Performance] CPU cores: {cpu_count}, Available RAM: {available_gb:.1f}GB, Optimal workers: {optimal}")
            else:
                # Basic CPU-based threading
                optimal = min(cpu_count * 2, 16)  # 2x CPU cores, max 16
                print(f"[Stage 1 Performance] CPU cores: {cpu_count}, Optimal workers: {optimal}")
            
            return max(4, optimal)  # Minimum 4 workers
        except Exception as e:
            print(f"[Stage 1 Performance] Error calculating optimal workers: {e}, using default 8")
            return 8

    def _get_optimal_batch_size(self, total_pages: int) -> int:
        """Get optimal batch size based on PDF size"""
        try:
            if total_pages <= 50:
                return total_pages  # Single batch for small PDFs
            elif total_pages <= 200:
                return 50
            elif total_pages <= 500:
                return 75
            else:
                return 100  # Larger batches for big PDFs
        except Exception:
            return 50  # Default fallback

    def run(self):
        try:
            import fitz
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            self.progress.emit("Starting Stage 1 batch processing...")
            print("[Stage 1] Starting batch processing…")
            
            stage1 = self.config.get("processing_sequence", {}).get("stage_1", {})
            operations = stage1.get("operations", {})
            
            dpi_op = operations.get("dpi_adjustment", {})
            scaling_op = operations.get("page_scaling", {})
            margin_op = operations.get("pdf_margin_adjustment", {})
            # Log enabled operations and parameters
            print(f"[Stage 1] DPI adjustment: enabled={dpi_op.get('enabled', False)}, x_dpi={dpi_op.get('x_dpi', 300)}, y_dpi={dpi_op.get('y_dpi', 300)}")
            if scaling_op.get('enabled', False):
                print(
                    f"[Stage 1] Page scaling: enabled=True, target_width_mm={scaling_op.get('target_width_mm', 210)}, "
                    f"target_height_mm={scaling_op.get('target_height_mm', 297)}"
                )
            else:
                print(f"[Stage 1] Page scaling: enabled=False")
            print(
                f"[Stage 1] PDF margin adjustment: enabled={margin_op.get('enabled', False)}, "
                f"top={margin_op.get('top_margin', 0)}, bottom={margin_op.get('bottom_margin', 0)}, "
                f"left={margin_op.get('left_margin', 0)}, right={margin_op.get('right_margin', 0)}"
            )
            
            # Process each PDF
            for pdf_idx, pdf_path in enumerate(self.include_files):
                if self._cancelled:
                    raise Exception("Cancelled")
                pdf_name = os.path.basename(pdf_path)
                self.progress.emit(f"Processing {pdf_name} ({pdf_idx+1}/{len(self.include_files)})...")
                print(f"[Stage 1] Processing {pdf_name} ({pdf_idx+1}/{len(self.include_files)})…")
                
                # Open source PDF
                src_doc = fitz.open(pdf_path)
                total_pages = len(src_doc)
                
                # Use dynamic batch size based on PDF size
                optimal_batch_size = self._get_optimal_batch_size(total_pages)
                print(f"[Stage 1] {pdf_name}: {total_pages} pages, using batch size: {optimal_batch_size}")
                
                # Split into batches
                batches = []
                for start_page in range(0, total_pages, optimal_batch_size):
                    end_page = min(start_page + optimal_batch_size, total_pages)
                    batches.append((start_page, end_page))
                
                self.progress.emit(f"{pdf_name}: Processing {len(batches)} batches...")
                print(f"[Stage 1] {pdf_name}: Processing {len(batches)} batches…")
                
                # Process batches in parallel
                batch_outputs = []
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {}
                    for batch_idx, (start, end) in enumerate(batches):
                        future = executor.submit(
                            self._process_batch,
                            pdf_path, start, end, batch_idx,
                            dpi_op, scaling_op, margin_op
                        )
                        futures[future] = batch_idx
                    
                    # Collect results
                    for future in as_completed(futures):
                        if self._cancelled:
                            try:
                                executor.shutdown(cancel_futures=True)
                            except Exception:
                                pass
                            raise Exception("Cancelled")
                        batch_idx = futures[future]
                        try:
                            batch_output = future.result()
                            batch_outputs.append((batch_idx, batch_output))
                            self.progress.emit(f"{pdf_name}: Batch {batch_idx+1}/{len(batches)} complete")
                            print(f"[Stage 1] {pdf_name}: Batch {batch_idx+1}/{len(batches)} complete → {batch_output}")
                        except Exception as e:
                            src_doc.close()
                            raise Exception(f"Batch {batch_idx} failed: {e}")
                
                src_doc.close()
                
                # Sort by batch index
                batch_outputs.sort(key=lambda x: x[0])
                
                # Merge batches into final PDF
                self.progress.emit(f"{pdf_name}: Merging batches...")
                print(f"[Stage 1] {pdf_name}: Merging {len(batch_outputs)} batches…")
                # Ensure unique filename to avoid collisions (same basename from different sources)
                def _unique_path(dst_path: str) -> str:
                    try:
                        if not os.path.exists(dst_path):
                            return dst_path
                        base_dir = os.path.dirname(dst_path)
                        base = os.path.basename(dst_path)
                        name, ext = os.path.splitext(base)
                        c = 1
                        while True:
                            cand = os.path.join(base_dir, f"{name}_{c}{ext}")
                            if not os.path.exists(cand):
                                return cand
                            c += 1
                    except Exception:
                        return dst_path
                # Create final output with _prep suffix
                base_name = os.path.splitext(pdf_name)[0]
                final_name = f"{base_name}_prep.pdf"
                final_output = _unique_path(os.path.join(self.output_folder, final_name))
                self._merge_batches([path for _, path in batch_outputs], final_output)
                
                # Cleanup batch files
                for _, batch_path in batch_outputs:
                    try:
                        os.remove(batch_path)
                    except:
                        pass
                
                self.progress.emit(f"{pdf_name}: Complete")
                print(f"[Stage 1] {pdf_name}: Complete → {final_output}")
            
            self.progress.emit("Stage 1 processing completed successfully!")
            self.success.emit(self.output_folder)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def cancel(self):
        try:
            self._cancelled = True
        except Exception:
            self._cancelled = True

    def _process_batch(self, pdf_path: str, start_page: int, end_page: int, batch_idx: int,
                   dpi_op: dict, scaling_op: dict, margin_op: dict) -> str:
        """Process a single batch of pages with correct logic from external modules"""
        import fitz
        
        try:
            if getattr(self, '_cancelled', False):
                raise Exception("Cancelled")
            src_doc = fitz.open(pdf_path)
            out_doc = fitz.open()
            
            # Process each page in batch
            for page_num in range(start_page, end_page):
                if getattr(self, '_cancelled', False):
                    src_doc.close()
                    out_doc.close()
                    raise Exception("Cancelled")
                page = src_doc.load_page(page_num)
                
                # === STEP 1: DPI ADJUSTMENT (skip if scaling is enabled to avoid double rasterization) ===
                scale_enabled = scaling_op.get("enabled", False)
                if dpi_op.get("enabled", False) and not scale_enabled:
                    x_dpi = dpi_op.get("x_dpi", 300)
                    y_dpi = dpi_op.get("y_dpi", 300)
                    
                    scale_x = max(1.0, float(x_dpi) / 72.0)
                    scale_y = max(1.0, float(y_dpi) / 72.0)
                    mat = fitz.Matrix(scale_x, scale_y)
                    
                    pix = page.get_pixmap(matrix=mat)
                    
                    new_page = out_doc.new_page(
                        width=page.rect.width,
                        height=page.rect.height
                    )
                    new_page.insert_image(new_page.rect, pixmap=pix)
                    pix = None
                    # Log DPI application
                    print(
                        f"[Stage 1][{os.path.basename(pdf_path)}] Page {page_num+1}: DPI applied → X:{x_dpi}, Y:{y_dpi}"
                    )
                else:
                    # No DPI - just copy page
                    out_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)
                
                # === STEP 2: SCALING to absolute size (width/height in mm) ===
                if scaling_op.get("enabled", False):
                    target_w_mm = scaling_op.get("target_width_mm")
                    target_h_mm = scaling_op.get("target_height_mm")
                    if isinstance(target_w_mm, (int, float)) and isinstance(target_h_mm, (int, float)) \
                       and target_w_mm > 0 and target_h_mm > 0:
                        # Get the last added page (from step 1 or inserted copy)
                        last_page_num = len(out_doc) - 1
                        temp_doc = fitz.open()
                        temp_doc.insert_pdf(out_doc, from_page=last_page_num, to_page=last_page_num)
                        # Remove the existing page
                        out_doc.delete_page(last_page_num)
                        # Convert mm to points
                        mm_to_points = 2.834645669
                        new_width = float(target_w_mm) * mm_to_points
                        new_height = float(target_h_mm) * mm_to_points
                        # Create new page with requested size and draw the previous page stretched to fill.
                        # Rasterize at a high DPI to avoid quality loss while allowing non-uniform stretch
                        new_page = out_doc.new_page(width=new_width, height=new_height)
                        src_page = temp_doc[0]
                        # Use DPI from DPI operation if set; otherwise default 300
                        if dpi_op.get("enabled", False):
                            desired_dpi = float(max(dpi_op.get("x_dpi", 300), dpi_op.get("y_dpi", 300)))
                        else:
                            desired_dpi = 300.0
                        dpi_scale = desired_dpi / 72.0
                        scale_x = (new_width / src_page.rect.width) * dpi_scale
                        scale_y = (new_height / src_page.rect.height) * dpi_scale
                        mat = fitz.Matrix(scale_x, scale_y)
                        pix = src_page.get_pixmap(matrix=mat, alpha=False)
                        new_page.insert_image(fitz.Rect(0, 0, new_width, new_height), pixmap=pix)
                        pix = None
                        temp_doc.close()
                        print(
                            f"[Stage 1][{os.path.basename(pdf_path)}] Page {page_num+1}: Scaled to {target_w_mm}×{target_h_mm} mm"
                        )
                
                # === STEP 3: MARGINS (from pdf_margin_adjustment.py lines 54-107) ===
                if margin_op.get("enabled", False):
                    top_margin = margin_op.get("top_margin", 0)
                    bottom_margin = margin_op.get("bottom_margin", 0)
                    left_margin = margin_op.get("left_margin", 0)
                    right_margin = margin_op.get("right_margin", 0)
                    
                    if top_margin != 0 or bottom_margin != 0 or left_margin != 0 or right_margin != 0:
                        mm_to_points = 2.834645669
                        
                        # Get the last added page
                        last_page_num = len(out_doc) - 1
                        temp_doc = fitz.open()
                        temp_doc.insert_pdf(out_doc, from_page=last_page_num, to_page=last_page_num)
                        
                        original_rect = temp_doc[0].rect
                        
                        top_adj = top_margin * mm_to_points
                        bottom_adj = bottom_margin * mm_to_points
                        left_adj = left_margin * mm_to_points
                        right_adj = right_margin * mm_to_points
                        
                        new_width = original_rect.width + left_adj + right_adj
                        new_height = original_rect.height + top_adj + bottom_adj
                        new_width = max(new_width, 72)
                        new_height = max(new_height, 72)
                        
                        # Remove old page
                        out_doc.delete_page(last_page_num)
                        
                        # Create new page with margins
                        new_page = out_doc.new_page(width=new_width, height=new_height)
                        
                        src_x0 = max(0, -left_adj)
                        src_y0 = max(0, -top_adj)
                        src_x1 = min(original_rect.width, original_rect.width - right_adj)
                        src_y1 = min(original_rect.height, original_rect.height - bottom_adj)
                        
                        dest_x0 = max(0, left_adj)
                        dest_y0 = max(0, top_adj)
                        dest_x1 = dest_x0 + (src_x1 - src_x0)
                        dest_y1 = dest_y0 + (src_y1 - src_y0)
                        
                        src_rect = fitz.Rect(src_x0, src_y0, src_x1, src_y1)
                        dest_rect = fitz.Rect(dest_x0, dest_y0, dest_x1, dest_y1)
                        
                        if src_rect.width > 0 and src_rect.height > 0:
                            new_page.show_pdf_page(dest_rect, temp_doc, 0, clip=src_rect)
                        
                        temp_doc.close()
                        # Log margin adjustment
                        print(
                            f"[Stage 1][{os.path.basename(pdf_path)}] Page {page_num+1}: Margins T:{top_margin} B:{bottom_margin} L:{left_margin} R:{right_margin} (mm)"
                        )
                
                page = None
            
            src_doc.close()
            
            # Save batch
            batch_filename = f"batch_{batch_idx:04d}.pdf"
            batch_path = os.path.join(self.output_folder, batch_filename)
            out_doc.save(batch_path, garbage=4, deflate=True)
            out_doc.close()
            print(
                f"[Stage 1][{os.path.basename(pdf_path)}] Saved batch {batch_idx+1} ({start_page+1}-{end_page}) → {batch_path}"
            )
            
            return batch_path
            
        except Exception as e:
            raise Exception(f"Batch processing error: {e}")

    def _merge_batches(self, batch_paths: list, output_path: str):
        """Merge all batch PDFs into final output - FULLY OPTIMIZED for 6000+ pages"""
        import fitz
        import time
        
        try:
            print(f"[Stage 1] Starting merge of {len(batch_paths)} batches...")
            merge_start = time.time()
            
            final_doc = fitz.open()
            
            # FASTEST: Insert entire batch PDF at once (no page loop)
            for idx, batch_path in enumerate(batch_paths, 1):
                batch_start = time.time()
                batch_doc = fitz.open(batch_path)
                page_count = len(batch_doc)
                
                print(f"[Stage 1] Merging batch {idx}/{len(batch_paths)} ({page_count} pages)...")
                
                # Insert ALL pages from batch in one call
                final_doc.insert_pdf(batch_doc)
                batch_doc.close()
                
                batch_time = time.time() - batch_start
                print(f"[Stage 1] Batch {idx} merged in {batch_time:.2f}s")
            
            total_pages = len(final_doc)
            print(f"[Stage 1] All batches merged. Saving final PDF ({total_pages} total pages)...")
            print(f"[Stage 1] Output path: {output_path}")
            save_start = time.time()
            
            # OPTIMIZED SAVE: Use faster settings for large PDFs
            if total_pages > 1000:
                print(f"[Stage 1] Large PDF detected ({total_pages} pages) - using fast save mode...")
                print(f"[Stage 1] Using garbage=3, deflate=True for faster processing...")
                print(f"[Stage 1] Writing PDF to disk... (this may take a while for large files)")

                # Now save WITH GIL yielding
                import threading, gc, time
                save_complete = False

                def save_with_progress():
                    nonlocal save_complete
                    final_doc.save(output_path, garbage=1, deflate=True)
                    save_complete = True

                save_thread = threading.Thread(target=save_with_progress)
                save_thread.start()

                # Emit progress while save is running
                while not save_complete:
                    self.progress.emit(f"Saving PDF... ({total_pages} pages)")
                    time.sleep(0.5)  # Yield GIL to keep GUI responsive
                    try:
                        gc.collect()
                    except Exception:
                        pass

                save_thread.join()

                print(f"[Stage 1] PDF write completed!")
            else:
                # Same for smaller PDFs
                print(f"[Stage 1] Standard PDF ({total_pages} pages) - using full optimization...")
                print(f"[Stage 1] Writing PDF to disk...")

                import threading, gc, time
                save_complete = False

                def save_with_progress_small():
                    nonlocal save_complete
                    final_doc.save(output_path, garbage=4, deflate=True)
                    save_complete = True

                save_thread_small = threading.Thread(target=save_with_progress_small)
                save_thread_small.start()

                # Emit progress while save is running
                while not save_complete:
                    self.progress.emit(f"Saving PDF... ({total_pages} pages)")
                    time.sleep(0.5)
                    try:
                        gc.collect()
                    except Exception:
                        pass

                save_thread_small.join()

                print(f"[Stage 1] PDF write completed!")
            
            final_doc.close()
            
            save_time = time.time() - save_start
            total_time = time.time() - merge_start
            
            print(f"[Stage 1] ✓ Final PDF saved in {save_time:.2f}s ({save_time/60:.2f} minutes)")
            print(f"[Stage 1] ✓ Total merge time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
            print(f"[Stage 1] ✓ Output: {output_path}")
            
        except Exception as e:
            raise Exception(f"Batch merge error: {e}")


class _Stage2ProcessingWorker(QObject):
    """Worker for Stage 2 processing (Rotation + Reverse + Add Pages)"""
    finished = Signal()
    error = Signal(str)
    progress = Signal(str)
    success = Signal(str)

    def __init__(self, include_files: list, output_folder: str, config: dict, final_output_folder: str):
        super().__init__()
        self.include_files = include_files
        self.output_folder = output_folder
        self.config = config
        self.final_output_folder = final_output_folder
        self._cancelled = False

    def run(self):
        try:
            import fitz
            
            self.progress.emit("Starting Stage 2 processing...")
            print("[Stage 2] Starting document structure processing...")
            
            stage2 = self.config.get("processing_sequence", {}).get("stage_2", {})
            operations = stage2.get("operations", {})
            
            rotation_op = operations.get("rotation", {})
            reverse_op = operations.get("reverse_ordering", {})
            append_op = operations.get("add_blank_pages", {})
            
            rotation_enabled = rotation_op.get("enabled", False)
            reverse_enabled = reverse_op.get("enabled", False)
            append_enabled = append_op.get("enabled", False)
            
            print(f"[Stage 2] Rotation: enabled={rotation_enabled}")
            print(f"[Stage 2] Reverse: enabled={reverse_enabled}")
            print(f"[Stage 2] Add Pages: enabled={append_enabled}")
            
            # Ensure final folder exists
            os.makedirs(self.final_output_folder, exist_ok=True)

            # Process each PDF file
            for pdf_idx, pdf_path in enumerate(self.include_files):
                if self._cancelled:
                    raise Exception("Cancelled")
                pdf_name = os.path.basename(pdf_path)
                self.progress.emit(f"Processing {pdf_name} ({pdf_idx+1}/{len(self.include_files)})...")
                print(f"[Stage 2] Processing {pdf_name} ({pdf_idx+1}/{len(self.include_files)})...")
                
                current_input = pdf_path
                temp_files = []
                
                try:
                    # Step 1: Rotation (use local helper module)
                    if rotation_enabled:
                        angle = rotation_op.get("angle", 0)
                        if angle != 0:
                            if self._cancelled:
                                raise Exception("Cancelled")
                            try:
                                from .pdf_rotate_pages import rotate_pdf
                            except Exception:
                                from pages.PDF_colour_conversion.pdf_rotate_pages import rotate_pdf
                            name_noext, _ = os.path.splitext(pdf_name)
                            temp_output = os.path.join(self.output_folder, f"{name_noext}_rotated.pdf")
                            ok = rotate_pdf(current_input, temp_output, angle)
                            if not ok:
                                raise Exception("Rotation failed")
                            if current_input != pdf_path:
                                temp_files.append(current_input)
                            current_input = temp_output
                            print(f"[Stage 2] Applied rotation {angle}° to {pdf_name}")
                    
                    # Step 2: Reverse (use local helper module)
                    if reverse_enabled:
                        if self._cancelled:
                            raise Exception("Cancelled")
                        try:
                            from .pdf_reverse_pages import reverse_pdf
                        except Exception:
                            from pages.PDF_colour_conversion.pdf_reverse_pages import reverse_pdf
                        name_noext, _ = os.path.splitext(pdf_name)
                        temp_output = os.path.join(self.output_folder, f"{name_noext}_reversed.pdf")
                        reverse_pdf(current_input, temp_output)
                        if current_input != pdf_path:
                            temp_files.append(current_input)
                        current_input = temp_output
                        print(f"[Stage 2] Applied reverse to {pdf_name}")
                    
                    # Step 3: Add Pages (fallback internal implementation)
                    if append_enabled:
                        if self._cancelled:
                            raise Exception("Cancelled")
                        pages_to_append = append_op.get("pages_to_append", 1)
                        mode = append_op.get("mode", 0)
                        after_page = append_op.get("after_page", -1)
                        name_noext, _ = os.path.splitext(pdf_name)
                        # Save final output in the selected final output folder using original name
                        def _unique_path(dst_path: str) -> str:
                            try:
                                if not os.path.exists(dst_path):
                                    return dst_path
                                base_dir = os.path.dirname(dst_path)
                                base = os.path.basename(dst_path)
                                name, ext = os.path.splitext(base)
                                c = 1
                                while True:
                                    cand = os.path.join(base_dir, f"{name}_{c}{ext}")
                                    if not os.path.exists(cand):
                                        return cand
                                    c += 1
                            except Exception:
                                return dst_path
                        # Create final output with _prep suffix
                        base_name = os.path.splitext(pdf_name)[0]
                        final_name = f"{base_name}_prep.pdf"
                        final_output = _unique_path(os.path.join(self.final_output_folder, final_name))
                        # Minimal synchronous append implementation using fitz
                        src = fitz.open(current_input)
                        try:
                            if len(src) == 0:
                                raise Exception("Source PDF has no pages")
                            last = src[-1]
                            width = last.rect.width
                            height = last.rect.height
                            dst = fitz.open()
                            if mode == 0:
                                dst.insert_pdf(src)
                                for _ in range(pages_to_append):
                                    dst.new_page(width=width, height=height)
                            elif mode == 1:
                                insert_after = max(1, min(after_page if after_page > 0 else 1, len(src)))
                                for i in range(len(src)):
                                    dst.insert_pdf(src, from_page=i, to_page=i)
                                    if (i + 1) == insert_after:
                                        for _ in range(pages_to_append):
                                            dst.new_page(width=width, height=height)
                            else:
                                for i in range(len(src)):
                                    dst.insert_pdf(src, from_page=i, to_page=i)
                                    for _ in range(pages_to_append):
                                        dst.new_page(width=width, height=height)
                            dst.save(final_output)
                            dst.close()
                        finally:
                            src.close()
                        if current_input != pdf_path:
                            temp_files.append(current_input)
                        current_input = final_output
                        print(f"[Stage 2] Added {pages_to_append} pages to {pdf_name}")
                    else:
                        # No add pages - just copy to final output (in final folder)
                        def _unique_path(dst_path: str) -> str:
                            try:
                                if not os.path.exists(dst_path):
                                    return dst_path
                                base_dir = os.path.dirname(dst_path)
                                base = os.path.basename(dst_path)
                                name, ext = os.path.splitext(base)
                                c = 1
                                while True:
                                    cand = os.path.join(base_dir, f"{name}_{c}{ext}")
                                    if not os.path.exists(cand):
                                        return cand
                                    c += 1
                            except Exception:
                                return dst_path
                        # Create final output with _prep suffix
                        base_name = os.path.splitext(pdf_name)[0]
                        final_name = f"{base_name}_prep.pdf"
                        final_output = _unique_path(os.path.join(self.final_output_folder, final_name))
                        if current_input != final_output:
                            import shutil
                            shutil.copy2(current_input, final_output)
                            if current_input != pdf_path:
                                temp_files.append(current_input)
                    
                    # Clean up temporary files
                    for temp_file in temp_files:
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                    
                    print(f"[Stage 2] Completed {pdf_name}")
                    self.progress.emit(f"{pdf_name}: Complete")
                    print(f"[Stage 2] {pdf_name}: Complete → {final_output}")
                    
                except Exception as e:
                    print(f"[Stage 2] Error processing {pdf_name}: {e}")
                    # Clean up temp files on error
                    for temp_file in temp_files:
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                    raise e
            
            self.progress.emit("Stage 2 processing completed successfully!")
            self.success.emit(self.final_output_folder)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def cancel(self):
        try:
            self._cancelled = True
        except Exception:
            self._cancelled = True


if __name__ == "__main__":
    # Minimal harness to preview the section standalone
    from PySide6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    w = PDFColourConversionSection()
    w.setWindowTitle("PDF PREP - Section Preview")
    w.resize(600, 400)
    w.show()
    sys.exit(app.exec())


