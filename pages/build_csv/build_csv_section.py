from pathlib import Path
import os
import csv
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QScrollArea, QProgressBar,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QTextEdit, QSplitter
)
from PySide6.QtGui import QTextCursor


class CSVGenerationWorker(QObject):
    """Worker thread for CSV generation"""
    finished = Signal(bool, str)  # success, message
    progress = Signal(int, int, str)  # current, total, message
    
    def __init__(self, folders, output_folder, csv_names, recursive=True, sort_alpha=True):
        super().__init__()
        self.folders = folders  # List of folder paths
        self.output_folder = output_folder
        self.csv_names = csv_names  # List of CSV names corresponding to folders
        self.recursive = recursive
        self.sort_alpha = sort_alpha
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
    
    def run(self):
        """Generate CSV files from selected folders"""
        try:
            total_folders = len(self.folders)
            
            for idx, folder_path in enumerate(self.folders):
                if self._cancelled:
                    self.finished.emit(False, "CSV generation cancelled")
                    return
                
                folder = Path(folder_path)
                csv_name = self.csv_names[idx]
                
                self.progress.emit(idx, total_folders, f"Processing folder {idx + 1}/{total_folders}: {folder.name}")
                
                # Collect all files
                if self.recursive:
                    files = sorted(folder.rglob('*'))
                else:
                    files = sorted(folder.glob('*'))
                
                # Filter only files (not directories)
                files = [f for f in files if f.is_file()]
                
                # Sort alphabetically if requested
                if self.sort_alpha:
                    files = sorted(files, key=lambda x: str(x).lower())
                
                # Generate CSV
                csv_path = Path(self.output_folder) / csv_name
                if not csv_path.suffix:
                    csv_path = csv_path.with_suffix('.csv')
                
                with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    for file_path in files:
                        writer.writerow([str(file_path.resolve())])
                
                self.progress.emit(idx + 1, total_folders, f"Generated: {csv_path.name} ({len(files)} files)")
            
            self.finished.emit(True, f"Successfully generated {total_folders} CSV file(s)")
            
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")


class BuildCSVSection(QWidget):
    """Section for building CSV files from folder contents"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._selected_folders = []
    
    def _style_group_box(self, group_box):
        """Apply consistent styling to group boxes"""
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
        """Initialize the UI"""
        main_layout = QVBoxLayout(self)
        
        # Left side - Controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(25)
        
        # Mode Selection
        mode_group = QGroupBox("Operation Mode")
        self._style_group_box(mode_group)
        mode_layout = QVBoxLayout()
        
        self.mode_button_group = QButtonGroup(self)
        self.single_folder_radio = QRadioButton("Single Folder → Single CSV")
        self.multi_folder_radio = QRadioButton("Multiple Folders → Multiple CSVs")
        self.single_folder_radio.setChecked(True)
        
        self.mode_button_group.addButton(self.single_folder_radio, 0)
        self.mode_button_group.addButton(self.multi_folder_radio, 1)
        
        mode_layout.addWidget(self.single_folder_radio)
        mode_layout.addWidget(self.multi_folder_radio)
        mode_group.setLayout(mode_layout)
        controls_layout.addWidget(mode_group)
        
        # Connect mode change
        self.mode_button_group.buttonClicked.connect(self._on_mode_changed)
        
        # Folder Selection
        folder_group = QGroupBox("Folder Selection")
        self._style_group_box(folder_group)
        folder_layout = QVBoxLayout()
        
        self.folder_list = QListWidget()
        self.folder_list.setMinimumHeight(150)
        folder_layout.addWidget(self.folder_list)
        
        folder_buttons_layout = QHBoxLayout()
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.remove_folder_btn = QPushButton("Remove Selected")
        self.remove_folder_btn.clicked.connect(self._remove_folder)
        self.clear_folders_btn = QPushButton("Clear All")
        self.clear_folders_btn.clicked.connect(self._clear_folders)
        
        folder_buttons_layout.addWidget(self.add_folder_btn)
        folder_buttons_layout.addWidget(self.remove_folder_btn)
        folder_buttons_layout.addWidget(self.clear_folders_btn)
        folder_layout.addLayout(folder_buttons_layout)
        
        folder_group.setLayout(folder_layout)
        controls_layout.addWidget(folder_group)
        
        # Output Folder Selection
        output_group = QGroupBox("Output Folder (Where to save CSVs)")
        self._style_group_box(output_group)
        output_layout = QVBoxLayout()
        
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("Select output folder for CSV files...")
        self.output_folder_edit.setReadOnly(True)
        
        self.browse_output_btn = QPushButton("Browse Output Folder")
        self.browse_output_btn.clicked.connect(self._select_output_folder)
        
        output_layout.addWidget(self.output_folder_edit)
        output_layout.addWidget(self.browse_output_btn)
        output_group.setLayout(output_layout)
        controls_layout.addWidget(output_group)
        
        # CSV Naming
        naming_group = QGroupBox("CSV File Naming")
        self._style_group_box(naming_group)
        naming_layout = QVBoxLayout()
        
        # Single folder mode naming
        self.single_csv_name_label = QLabel("CSV Filename:")
        self.single_csv_name_edit = QLineEdit()
        self.single_csv_name_edit.setPlaceholderText("Enter CSV filename (e.g., file_list.csv)")
        self.single_csv_name_edit.setText("file_list.csv")
        
        # Multi folder mode naming
        self.multi_csv_prefix_label = QLabel("CSV Filename Prefix:")
        self.multi_csv_prefix_edit = QLineEdit()
        self.multi_csv_prefix_edit.setPlaceholderText("Enter prefix (e.g., folder_)")
        self.multi_csv_prefix_edit.setText("folder_")
        self.multi_csv_prefix_label.setVisible(False)
        self.multi_csv_prefix_edit.setVisible(False)
        
        naming_layout.addWidget(self.single_csv_name_label)
        naming_layout.addWidget(self.single_csv_name_edit)
        naming_layout.addWidget(self.multi_csv_prefix_label)
        naming_layout.addWidget(self.multi_csv_prefix_edit)
        
        naming_group.setLayout(naming_layout)
        controls_layout.addWidget(naming_group)
        
        # Options
        options_group = QGroupBox("Options")
        self._style_group_box(options_group)
        options_layout = QVBoxLayout()
        
        self.recursive_checkbox = QCheckBox("Include subdirectories (recursive)")
        self.recursive_checkbox.setChecked(True)
        
        self.sort_alpha_checkbox = QCheckBox("Sort files alphabetically")
        self.sort_alpha_checkbox.setChecked(True)
        
        options_layout.addWidget(self.recursive_checkbox)
        options_layout.addWidget(self.sort_alpha_checkbox)
        options_group.setLayout(options_layout)
        controls_layout.addWidget(options_group)
        
        # Progress
        progress_group = QGroupBox("Progress")
        self._style_group_box(progress_group)
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { color: #000000; font-weight: bold; }")
        
        self.progress_label = QLabel("Ready to generate CSV files")
        self.progress_label.setStyleSheet("color: #6c757d; font-style: italic;")
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label)
        progress_group.setLayout(progress_layout)
        controls_layout.addWidget(progress_group)
        
        # Actions
        actions_group = QGroupBox("Actions")
        self._style_group_box(actions_group)
        actions_layout = QVBoxLayout()
        
        self.generate_btn = QPushButton("Generate CSV Files")
        self.generate_btn.clicked.connect(self._start_generation)
        
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("StopButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_generation)
        
        self.open_output_btn = QPushButton("Open Output Folder")
        self.open_output_btn.clicked.connect(self._open_output_folder)
        
        actions_layout.addWidget(self.generate_btn)
        actions_layout.addWidget(self.stop_btn)
        actions_layout.addWidget(self.open_output_btn)
        actions_group.setLayout(actions_layout)
        controls_layout.addWidget(actions_group)
        
        # Bottom Preview Section (like split section)
        preview_splitter = QSplitter(Qt.Horizontal)
        
        # Left: Output Folder Tree View
        folder_tree_group = QGroupBox("Output Folder & CSV Files")
        self._style_group_box(folder_tree_group)
        folder_tree_layout = QVBoxLayout()
        
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabel("Generated CSV Files")
        self.folder_tree.setMinimumHeight(400)
        self.folder_tree.setStyleSheet("QTreeWidget { color: #000000; }")
        self.folder_tree.itemSelectionChanged.connect(self._on_csv_file_selected)
        folder_tree_layout.addWidget(self.folder_tree)
        
        refresh_tree_btn = QPushButton("Refresh CSV List")
        refresh_tree_btn.clicked.connect(self._refresh_output_tree)
        folder_tree_layout.addWidget(refresh_tree_btn)
        
        folder_tree_group.setLayout(folder_tree_layout)
        preview_splitter.addWidget(folder_tree_group)
        
        # Right: CSV Preview
        csv_preview_group = QGroupBox("CSV Content Preview")
        self._style_group_box(csv_preview_group)
        csv_preview_layout = QVBoxLayout()
        
        self.csv_preview_text = QTextEdit()
        self.csv_preview_text.setReadOnly(True)
        self.csv_preview_text.setMinimumHeight(400)
        self.csv_preview_text.setPlaceholderText("CSV content preview will appear here...\n\nClick 'Refresh File List' to see files from selected folders.")
        self.csv_preview_text.setStyleSheet("font-family: 'Courier New', monospace;")
        csv_preview_layout.addWidget(self.csv_preview_text)
        
        csv_preview_group.setLayout(csv_preview_layout)
        preview_splitter.addWidget(csv_preview_group)
        
        # Set splitter proportions (40% folder tree, 60% CSV preview)
        preview_splitter.setStretchFactor(0, 4)
        preview_splitter.setStretchFactor(1, 6)
        preview_splitter.setMinimumHeight(450)
        
        # Add preview section to controls layout (so it's all together)
        controls_layout.addWidget(preview_splitter)
        
        # Make entire page scrollable
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page_scroll.setWidget(controls_widget)
        
        main_layout.addWidget(page_scroll)
    
    def _on_mode_changed(self):
        """Handle mode change between single and multi folder"""
        is_single = self.single_folder_radio.isChecked()
        
        # Show/hide appropriate naming controls
        self.single_csv_name_label.setVisible(is_single)
        self.single_csv_name_edit.setVisible(is_single)
        self.multi_csv_prefix_label.setVisible(not is_single)
        self.multi_csv_prefix_edit.setVisible(not is_single)
    
    def _add_folder(self):
        """Add a folder to the list"""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", os.getcwd())
        if folder:
            # Check if already added
            if folder not in self._selected_folders:
                self._selected_folders.append(folder)
                self.folder_list.addItem(folder)
            else:
                QMessageBox.information(self, "Already Added", "This folder is already in the list.")
    
    def _remove_folder(self):
        """Remove selected folder from the list"""
        current_row = self.folder_list.currentRow()
        if current_row >= 0:
            self._selected_folders.pop(current_row)
            self.folder_list.takeItem(current_row)
    
    def _clear_folders(self):
        """Clear all folders"""
        self._selected_folders.clear()
        self.folder_list.clear()
        # Clear tree and preview when folders cleared
        self.folder_tree.clear()
        self.csv_preview_text.clear()
    
    def _select_output_folder(self):
        """Select output folder for CSV files"""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", os.getcwd())
        if folder:
            self.output_folder_edit.setText(folder)
            # Auto-refresh tree to show existing CSV files if any
            self._refresh_output_tree()
    
    def _start_generation(self):
        """Start CSV generation"""
        # Validation
        if not self._selected_folders:
            QMessageBox.warning(self, "No Folders", "Please add at least one folder to scan.")
            return
        
        output_folder = self.output_folder_edit.text().strip()
        if not output_folder:
            QMessageBox.warning(self, "No Output Folder", "Please select an output folder for CSV files.")
            return
        
        # Prepare CSV names
        csv_names = []
        if self.single_folder_radio.isChecked():
            # Single folder mode
            csv_name = self.single_csv_name_edit.text().strip()
            if not csv_name:
                csv_name = "file_list.csv"
            csv_names = [csv_name]
        else:
            # Multi folder mode
            prefix = self.multi_csv_prefix_edit.text().strip()
            for folder in self._selected_folders:
                folder_name = Path(folder).name
                csv_name = f"{prefix}{folder_name}.csv"
                csv_names.append(csv_name)
        
        # Disable controls
        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Create worker
        self.csv_thread = QThread()
        self.csv_worker = CSVGenerationWorker(
            folders=self._selected_folders,
            output_folder=output_folder,
            csv_names=csv_names,
            recursive=self.recursive_checkbox.isChecked(),
            sort_alpha=self.sort_alpha_checkbox.isChecked()
        )
        self.csv_worker.moveToThread(self.csv_thread)
        
        # Connect signals
        self.csv_thread.started.connect(self.csv_worker.run)
        self.csv_worker.finished.connect(self.csv_thread.quit)
        self.csv_worker.finished.connect(self.csv_worker.deleteLater)
        self.csv_thread.finished.connect(self.csv_thread.deleteLater)
        self.csv_worker.progress.connect(self._update_progress)
        self.csv_worker.finished.connect(self._generation_finished)
        
        # Start
        self.csv_thread.start()
    
    def _stop_generation(self):
        """Stop CSV generation"""
        if hasattr(self, 'csv_worker') and self.csv_worker:
            self.csv_worker.cancel()
            self.progress_label.setText("Stopping...")
            self.stop_btn.setEnabled(False)
    
    def _update_progress(self, current, total, message):
        """Update progress"""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
        self.progress_label.setText(message)
    
    def _generation_finished(self, success, message):
        """Handle generation finished"""
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if success:
            self.progress_bar.setValue(100)
            self.progress_label.setText(message)
            # Auto-refresh output tree to show generated CSV files
            self._refresh_output_tree()
            QMessageBox.information(self, "Success", message)
        else:
            self.progress_bar.setValue(0)
            self.progress_label.setText(message)
            if "cancel" not in message.lower():
                QMessageBox.warning(self, "Error", message)
    
    def _open_output_folder(self):
        """Open the output folder"""
        output_folder = self.output_folder_edit.text().strip()
        if output_folder and os.path.exists(output_folder):
            try:
                if os.name == 'nt':
                    os.startfile(output_folder)
                elif os.name == 'posix':
                    os.system(f"xdg-open '{output_folder}'")
                else:
                    os.system(f"open '{output_folder}'")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not open folder: {e}")
        else:
            QMessageBox.warning(self, "No Folder", "Please select an output folder first.")
    
    def _refresh_output_tree(self):
        """Refresh the tree with CSV files from output folder"""
        self.folder_tree.clear()
        self.csv_preview_text.clear()
        
        output_folder = self.output_folder_edit.text().strip()
        if not output_folder or not os.path.exists(output_folder):
            return
        
        output_path = Path(output_folder)
        
        # Create output folder item
        output_item = QTreeWidgetItem(self.folder_tree)
        output_item.setText(0, f"📁 {output_path.name}")
        output_item.setData(0, Qt.UserRole, str(output_path))
        
        # Get all CSV files in output folder
        csv_files = sorted(output_path.glob("*.csv"))
        
        # Add CSV files to tree
        for csv_file in csv_files:
            csv_item = QTreeWidgetItem(output_item)
            csv_item.setText(0, f"📄 {csv_file.name}")
            csv_item.setData(0, Qt.UserRole, str(csv_file.resolve()))
        
        output_item.setExpanded(True)
    
    def _on_csv_file_selected(self):
        """Handle selection change in CSV file tree"""
        selected_items = self.folder_tree.selectedItems()
        if not selected_items:
            return
        
        item = selected_items[0]
        file_path = item.data(0, Qt.UserRole)
        
        # If it's the output folder item (parent), show all CSV files
        if item.childCount() > 0:
            self.csv_preview_text.setPlainText("Select a CSV file to preview its contents")
        # If it's a CSV file, show its contents
        elif file_path and file_path.endswith('.csv'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.csv_preview_text.setPlainText(content)
            except Exception as e:
                self.csv_preview_text.setPlainText(f"Error reading CSV file: {e}")
    
    def closeEvent(self, event):
        """Handle close event"""
        try:
            if hasattr(self, 'csv_worker') and self.csv_worker:
                self.csv_worker.cancel()
            if hasattr(self, 'csv_thread') and self.csv_thread.isRunning():
                self.csv_thread.quit()
                self.csv_thread.wait(500)
        except Exception:
            pass
        super().closeEvent(event)

