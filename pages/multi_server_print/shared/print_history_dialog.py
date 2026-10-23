"""
Print History Dialog

View and export print history from the database.
Accessible from Admin Panel.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
from pathlib import Path


class PrintHistoryDialog(QDialog):
    """Dialog to view and export print history"""
    
    def __init__(self, parent=None):
        """
        Initialize print history dialog.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.setWindowTitle("Print History")
        self.setModal(True)
        self.resize(1200, 700)  # Larger size to avoid horizontal scrollbar
        
        self._init_ui()
        self._load_history()
    
    def _init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        
        # Header
        header_label = QLabel("Print History - Recent 100 Records")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        layout.addWidget(header_label)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Filename", "File Path", "Print Date/Time", "Server", "Mode"
        ])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        
        # Set text color to black for visibility
        self.table.setStyleSheet("""
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
        self.table.setShowGrid(True)
        
        # Enable column sorting (click headers to sort)
        self.table.setSortingEnabled(True)
        
        layout.addWidget(self.table)
        
        # Stats label
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("padding: 5px; color: #666;")
        layout.addWidget(self.stats_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_history)
        button_layout.addWidget(refresh_btn)
        
        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self._export_history)
        button_layout.addWidget(export_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def _load_history(self):
        """Load print history from database"""
        try:
            from .print_history_db import PrintHistoryDB
            
            db = PrintHistoryDB()
            history = db.get_history(limit=100)
            stats = db.get_stats()
            
            # Update table
            self.table.setRowCount(len(history))
            
            for row, record in enumerate(history):
                # Filename
                filename_item = QTableWidgetItem(record['filename'])
                self.table.setItem(row, 0, filename_item)
                
                # File path
                path_item = QTableWidgetItem(record['file_path'])
                self.table.setItem(row, 1, path_item)
                
                # Print timestamp (format for readability)
                timestamp = record['print_timestamp']
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp)
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_time = timestamp
                
                time_item = QTableWidgetItem(formatted_time)
                self.table.setItem(row, 2, time_item)
                
                # Server name
                server_item = QTableWidgetItem(record['server_name'])
                self.table.setItem(row, 3, server_item)
                
                # Mode
                mode_item = QTableWidgetItem(record['mode'])
                self.table.setItem(row, 4, mode_item)
            
            # Auto-resize columns
            self.table.resizeColumnsToContents()
            self.table.horizontalHeader().setStretchLastSection(True)
            
            # Update stats
            total = stats['total_records']
            oldest = stats['oldest_record']
            newest = stats['newest_record']
            
            if oldest and newest:
                try:
                    from datetime import datetime
                    oldest_dt = datetime.fromisoformat(oldest)
                    newest_dt = datetime.fromisoformat(newest)
                    stats_text = (
                        f"Total Records: {total} | "
                        f"Oldest: {oldest_dt.strftime('%Y-%m-%d')} | "
                        f"Newest: {newest_dt.strftime('%Y-%m-%d')}"
                    )
                except:
                    stats_text = f"Total Records: {total}"
            else:
                stats_text = f"Total Records: {total}"
            
            self.stats_label.setText(stats_text)
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load print history:\n{str(e)}"
            )
    
    def _export_history(self):
        """Export history to CSV file"""
        try:
            # Ask user for save location
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Print History",
                str(Path.home() / "print_history.csv"),
                "CSV Files (*.csv)"
            )
            
            if not file_path:
                return  # User cancelled
            
            # Export to CSV
            from .print_history_db import PrintHistoryDB
            
            db = PrintHistoryDB()
            success = db.export_to_csv(file_path)
            
            if success:
                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Print history exported to:\n{file_path}"
                )
            else:
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    "Failed to export print history to CSV."
                )
                
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to export print history:\n{str(e)}"
            )
