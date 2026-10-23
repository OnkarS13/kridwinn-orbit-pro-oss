"""
Reprint Warning Dialog

Shown when duplicate files are detected in "Warning" mode.
Displays list of files that have been printed before and allows user to proceed or cancel.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QCheckBox
)
from PySide6.QtCore import Qt
from typing import List, Dict


class ReprintWarningDialog(QDialog):
    """Dialog to warn about duplicate files"""
    
    def __init__(self, duplicates: List[Dict], parent=None):
        """
        Initialize reprint warning dialog.
        
        Args:
            duplicates: List of duplicate file info dicts with keys:
                - filename: str
                - file_path: str
                - print_timestamp: str
                - server_name: str
            parent: Parent widget
        """
        super().__init__(parent)
        self.duplicates = duplicates
        self.dont_show_again = False
        
        self.setWindowTitle("Reprint Warning")
        self.setModal(True)
        self.resize(700, 400)
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        
        # Warning message
        warning_label = QLabel(
            "⚠️ The following files have already been printed:\n"
            "Printing them again may result in duplicate output."
        )
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("font-weight: bold; color: #ff6b00; padding: 10px;")
        layout.addWidget(warning_label)
        
        # Table of duplicates
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Filename", "Last Printed", "Server"])
        table.setRowCount(len(self.duplicates))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        
        # Set text color to black and add grid lines
        table.setStyleSheet("""
            QTableWidget {
                color: black;
                background-color: white;
                gridline-color: black;
            }
            QTableWidget::item {
                color: black;
                border: 1px solid black;
            }
            QHeaderView::section {
                color: black;
                background-color: #f0f0f0;
                font-weight: bold;
                border: 1px solid black;
            }
        """)
        
        # Show grid lines
        table.setShowGrid(True)
        
        for row, dup in enumerate(self.duplicates):
            # Filename
            filename_item = QTableWidgetItem(dup['filename'])
            table.setItem(row, 0, filename_item)
            
            # Print timestamp (format for readability)
            timestamp = dup['print_timestamp']
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp)
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                formatted_time = timestamp
            
            time_item = QTableWidgetItem(formatted_time)
            table.setItem(row, 1, time_item)
            
            # Server name
            server_item = QTableWidgetItem(dup['server_name'])
            table.setItem(row, 2, server_item)
        
        # Auto-resize columns
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        
        layout.addWidget(table)
        
        # Don't show again checkbox
        self.dont_show_checkbox = QCheckBox("Don't show this warning again for this session")
        layout.addWidget(self.dont_show_checkbox)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        proceed_btn = QPushButton("Print Anyway")
        proceed_btn.setStyleSheet("background-color: #ff6b00; color: white; font-weight: bold;")
        proceed_btn.clicked.connect(self._on_proceed)
        button_layout.addWidget(proceed_btn)
        
        layout.addLayout(button_layout)
    
    def _on_proceed(self):
        """Handle proceed button click"""
        self.dont_show_again = self.dont_show_checkbox.isChecked()
        self.accept()
