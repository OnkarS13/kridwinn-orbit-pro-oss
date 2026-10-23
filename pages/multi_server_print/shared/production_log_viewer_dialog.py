"""
Production Log Viewer Dialog

View and export production logs from CSV files.
Accessible from Admin Panel's Production Logging section.
"""

import csv
from pathlib import Path
from typing import Dict, List
from datetime import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QDateEdit, QComboBox, QWidget, QGridLayout
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QIcon


class ProductionLogViewerDialog(QDialog):
    """Dialog to view and export production logs from CSV files"""

    def __init__(self, parent=None):
        """
        Initialize production log viewer dialog.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle("Production Log Viewer")
        self.setModal(True)
        self.resize(1400, 700)

        # Load current settings
        self._load_current_settings()

        # Initialize UI
        self._init_ui()

        # Load today's log by default
        self._load_and_display_log()

    def _load_current_settings(self):
        """Load current logging mode from admin settings"""
        try:
            from .admin_config import AdminConfigManager
            config_manager = AdminConfigManager()
            settings = config_manager.load_settings()

            self.logging_mode = settings.logging_mode  # 'daily', 'monthly', or 'yearly'
            self.logging_enabled = settings.logging_enabled

        except Exception as e:
            print(f"Error loading admin settings: {e}")
            self.logging_mode = "daily"  # Default to daily
            self.logging_enabled = True

    def _init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)

        # Header with mode indicator
        header_label = QLabel(f"Production Log Viewer - {self.logging_mode.capitalize()} Mode")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        layout.addWidget(header_label)

        # Date picker row
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Select Date:"))

        date_picker_widget = self._create_date_picker()
        date_row.addWidget(date_picker_widget)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        date_row.addWidget(refresh_btn)

        date_row.addStretch()
        layout.addLayout(date_row)

        # Statistics panel
        stats_panel = self._create_statistics_panel()
        layout.addWidget(stats_panel)

        # Log table
        self.log_table = self._create_log_table()
        layout.addWidget(self.log_table)

        # Stats label (summary)
        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("padding: 5px; color: #666;")
        layout.addWidget(self.summary_label)

        # Buttons
        button_layout = QHBoxLayout()

        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self._on_export_clicked)
        button_layout.addWidget(export_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _create_date_picker(self) -> QWidget:
        """Create date picker widget based on logging mode"""
        if self.logging_mode == "daily":
            # Daily mode: QDateEdit with calendar popup
            self.date_picker = QDateEdit()
            self.date_picker.setCalendarPopup(True)
            self.date_picker.setDate(QDate.currentDate())
            self.date_picker.setDisplayFormat("yyyy-MM-dd")
            self.date_picker.dateChanged.connect(self._on_date_changed)
            # Set stylesheet to ensure black text on white background
            # Includes styling for the calendar popup widget
            self.date_picker.setStyleSheet("""
                QDateEdit {
                    color: black;
                    background-color: white;
                    border: 1px solid #ccc;
                    padding: 2px;
                }
                QDateEdit::drop-down {
                    border: none;
                }
                QCalendarWidget {
                    color: black;
                    background-color: white;
                }
                QCalendarWidget QTableView {
                    color: black;
                    background-color: white;
                    selection-background-color: #0078d4;
                    selection-color: white;
                }
                QCalendarWidget QHeaderView::section {
                    color: black;
                    background-color: #f0f0f0;
                    font-weight: bold;
                }
                QCalendarWidget QAbstractItemView:enabled {
                    color: black;
                    background-color: white;
                }
                QCalendarWidget QAbstractItemView:enabled:selected {
                    background-color: #0078d4;
                    color: white;
                }
                QCalendarWidget QSpinBox {
                    color: black;
                    background-color: white;
                }
                QCalendarWidget QToolButton {
                    color: black;
                    background-color: white;
                }
                QCalendarWidget QComboBox {
                    color: black;
                    background-color: white;
                    border: 1px solid #ccc;
                }
                QCalendarWidget QComboBox::drop-down {
                    border: none;
                }
                QCalendarWidget QComboBox QAbstractItemView {
                    color: black;
                    background-color: white;
                    selection-background-color: #0078d4;
                    selection-color: white;
                }
                QCalendarWidget QComboBox::item {
                    color: black;
                    background-color: white;
                }
                QCalendarWidget QComboBox::item:selected {
                    background-color: #0078d4;
                    color: white;
                }
                QCalendarWidget QMenu {
                    color: black;
                    background-color: white;
                }
                QCalendarWidget QMenu::item {
                    color: black;
                    background-color: white;
                    padding: 4px 20px;
                }
                QCalendarWidget QMenu::item:selected {
                    background-color: #0078d4;
                    color: white;
                }
            """)
            self.selected_date = self.date_picker.date()
            return self.date_picker

        elif self.logging_mode == "monthly":
            # Monthly mode: Two combo boxes (Month + Year)
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)

            # Month combo
            self.month_combo = QComboBox()
            self.month_combo.addItems([
                'January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'
            ])
            current_month = datetime.now().month
            self.month_combo.setCurrentIndex(current_month - 1)
            self.month_combo.currentIndexChanged.connect(self._on_date_changed)
            # Set stylesheet to ensure black text on white background
            self.month_combo.setStyleSheet("""
                QComboBox {
                    color: black;
                    background-color: white;
                    border: 1px solid #ccc;
                    padding: 2px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    color: black;
                    background-color: white;
                    selection-background-color: #0078d4;
                    selection-color: white;
                }
            """)
            layout.addWidget(self.month_combo)

            # Year combo
            self.year_combo = QComboBox()
            current_year = datetime.now().year
            years = [str(y) for y in range(current_year - 5, current_year + 2)]
            self.year_combo.addItems(years)
            self.year_combo.setCurrentText(str(current_year))
            self.year_combo.currentIndexChanged.connect(self._on_date_changed)
            # Set stylesheet to ensure black text on white background
            self.year_combo.setStyleSheet("""
                QComboBox {
                    color: black;
                    background-color: white;
                    border: 1px solid #ccc;
                    padding: 2px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    color: black;
                    background-color: white;
                    selection-background-color: #0078d4;
                    selection-color: white;
                }
            """)
            layout.addWidget(self.year_combo)

            self.selected_date = (current_month, current_year)
            return container

        else:  # yearly
            # Yearly mode: Single combo box (Year only)
            self.year_combo = QComboBox()
            current_year = datetime.now().year
            years = [str(y) for y in range(current_year - 5, current_year + 2)]
            self.year_combo.addItems(years)
            self.year_combo.setCurrentText(str(current_year))
            self.year_combo.currentIndexChanged.connect(self._on_date_changed)
            # Set stylesheet to ensure black text on white background
            self.year_combo.setStyleSheet("""
                QComboBox {
                    color: black;
                    background-color: white;
                    border: 1px solid #ccc;
                    padding: 2px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox QAbstractItemView {
                    color: black;
                    background-color: white;
                    selection-background-color: #0078d4;
                    selection-color: white;
                }
            """)
            self.selected_date = current_year
            return self.year_combo

    def _create_statistics_panel(self) -> QGroupBox:
        """Create statistics panel with QGroupBox"""
        group = QGroupBox("Log Statistics")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 6px;
                padding: 10px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QGridLayout()

        # Row 1
        layout.addWidget(QLabel("Total Prints:"), 0, 0)
        self.total_prints_label = QLabel("0")
        self.total_prints_label.setStyleSheet("font-weight: normal;")
        layout.addWidget(self.total_prints_label, 0, 1)

        layout.addWidget(QLabel("Total Pages:"), 0, 2)
        self.total_pages_label = QLabel("0")
        self.total_pages_label.setStyleSheet("font-weight: normal;")
        layout.addWidget(self.total_pages_label, 0, 3)

        # Row 2
        layout.addWidget(QLabel("Total Files:"), 1, 0)
        self.total_files_label = QLabel("0")
        self.total_files_label.setStyleSheet("font-weight: normal;")
        layout.addWidget(self.total_files_label, 1, 1)

        layout.addWidget(QLabel("Date Range:"), 1, 2)
        self.date_range_label = QLabel("N/A")
        self.date_range_label.setStyleSheet("font-weight: normal;")
        layout.addWidget(self.date_range_label, 1, 3)

        # Row 3
        layout.addWidget(QLabel("Servers:"), 2, 0)
        self.servers_label = QLabel("N/A")
        self.servers_label.setStyleSheet("font-weight: normal;")
        layout.addWidget(self.servers_label, 2, 1, 1, 3)

        # Row 4
        layout.addWidget(QLabel("Modes:"), 3, 0)
        self.modes_label = QLabel("N/A")
        self.modes_label.setStyleSheet("font-weight: normal;")
        layout.addWidget(self.modes_label, 3, 1, 1, 3)

        group.setLayout(layout)
        return group

    def _create_log_table(self) -> QTableWidget:
        """Create log table widget"""
        table = QTableWidget()
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels([
            "Timestamp", "Server", "Filename", "Pages", "Copies", "Total Prints", "Mode"
        ])

        # Match print_history_dialog.py styling
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

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setSortingEnabled(True)

        # Auto-resize columns
        table.horizontalHeader().setStretchLastSection(True)

        return table

    def _construct_log_path(self, selected_date) -> Path:
        """Construct log file path based on mode and date"""
        from .production_logger import ProductionLogger
        logger = ProductionLogger()

        if self.logging_mode == "daily":
            # selected_date is QDate object
            date_str = selected_date.toString("yyyy-MM-dd")
            filename = f"log_{date_str}.csv"
            return logger.daily_dir / filename

        elif self.logging_mode == "monthly":
            # selected_date is (month, year) tuple
            month, year = selected_date
            filename = f"log_{year}-{month:02d}.csv"
            return logger.monthly_dir / filename

        elif self.logging_mode == "yearly":
            # selected_date is year int
            year = selected_date
            filename = f"log_{year}.csv"
            return logger.yearly_dir / filename

        return Path()  # Fallback

    def _load_log_file(self, log_path: Path) -> List[Dict]:
        """Load and parse CSV log file"""
        if not log_path.exists():
            raise FileNotFoundError(f"No log file found: {log_path.name}")

        log_entries = []

        with open(log_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            # Validate headers
            expected = ['Timestamp', 'Server', 'Filename', 'Pages', 'Copies', 'Total_Prints', 'Mode']
            if not reader.fieldnames or reader.fieldnames != expected:
                raise ValueError("CSV file has unexpected or missing headers")

            for row in reader:
                log_entries.append(row)

        return log_entries

    def _calculate_statistics(self, log_data: List[Dict]) -> Dict:
        """Calculate statistics from log data"""
        if not log_data:
            return {
                'total_prints': 0, 'total_pages': 0, 'total_files': 0,
                'date_range': 'N/A', 'servers': {}, 'modes': {}
            }

        total_prints = sum(int(entry['Total_Prints']) for entry in log_data)
        total_pages = sum(int(entry['Pages']) * int(entry['Copies']) for entry in log_data)
        total_files = len(log_data)

        # Date range (sorted to ensure chronological order)
        timestamps = sorted([entry['Timestamp'] for entry in log_data])
        date_range = f"{timestamps[0]} to {timestamps[-1]}" if timestamps else "N/A"

        # Server breakdown
        servers = {}
        for entry in log_data:
            server = entry['Server']
            servers[server] = servers.get(server, 0) + int(entry['Total_Prints'])

        # Mode breakdown
        modes = {}
        for entry in log_data:
            mode = entry['Mode']
            modes[mode] = modes.get(mode, 0) + int(entry['Total_Prints'])

        return {
            'total_prints': total_prints,
            'total_pages': total_pages,
            'total_files': total_files,
            'date_range': date_range,
            'servers': servers,
            'modes': modes
        }

    def _populate_table_optimized(self, log_data: List[Dict]):
        """Populate table with performance optimization"""
        # Disable sorting during population
        self.log_table.setSortingEnabled(False)

        # Set row count once
        self.log_table.setRowCount(len(log_data))

        # Populate rows
        for row, entry in enumerate(log_data):
            self.log_table.setItem(row, 0, QTableWidgetItem(entry['Timestamp']))
            self.log_table.setItem(row, 1, QTableWidgetItem(entry['Server']))
            self.log_table.setItem(row, 2, QTableWidgetItem(entry['Filename']))
            self.log_table.setItem(row, 3, QTableWidgetItem(entry['Pages']))
            self.log_table.setItem(row, 4, QTableWidgetItem(entry['Copies']))
            self.log_table.setItem(row, 5, QTableWidgetItem(entry['Total_Prints']))
            self.log_table.setItem(row, 6, QTableWidgetItem(entry['Mode']))

        # Re-enable sorting
        self.log_table.setSortingEnabled(True)

        # Auto-resize columns
        self.log_table.resizeColumnsToContents()

    def _update_statistics_display(self, stats: Dict):
        """Update statistics labels with calculated data"""
        self.total_prints_label.setText(f"{stats['total_prints']:,}")
        self.total_pages_label.setText(f"{stats['total_pages']:,}")
        self.total_files_label.setText(f"{stats['total_files']:,}")
        self.date_range_label.setText(stats['date_range'])

        # Format server breakdown
        if stats['servers']:
            server_text = ", ".join([f"{s} ({c:,})" for s, c in stats['servers'].items()])
            self.servers_label.setText(server_text)
        else:
            self.servers_label.setText("N/A")

        # Format mode breakdown
        if stats['modes']:
            mode_text = ", ".join([f"{m} ({c:,})" for m, c in stats['modes'].items()])
            self.modes_label.setText(mode_text)
        else:
            self.modes_label.setText("N/A")

        # Update summary label
        self.summary_label.setText(
            f"Displaying {stats['total_files']:,} log entries | "
            f"Total Prints: {stats['total_prints']:,}"
        )

    def _clear_display(self):
        """Clear table and statistics display"""
        self.log_table.setRowCount(0)
        self.total_prints_label.setText("0")
        self.total_pages_label.setText("0")
        self.total_files_label.setText("0")
        self.date_range_label.setText("N/A")
        self.servers_label.setText("N/A")
        self.modes_label.setText("N/A")
        self.summary_label.setText("No data to display")

    def _load_and_display_log(self):
        """Load log file and display with performance check"""
        try:
            log_path = self._construct_log_path(self.selected_date)

            # Check file size
            if log_path.exists():
                file_size = log_path.stat().st_size
                if file_size > 1_000_000:  # > 1MB
                    file_size_mb = file_size / (1024 * 1024)
                    reply = QMessageBox.question(
                        self, "Large Log File",
                        f"This log file is {file_size_mb:.1f} MB.\n"
                        "Loading may take a moment. Continue?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        return

            # Load and display
            log_data = self._load_log_file(log_path)
            stats = self._calculate_statistics(log_data)
            self._update_statistics_display(stats)
            self._populate_table_optimized(log_data)

        except FileNotFoundError:
            QMessageBox.warning(self, "No Logs Found",
                "No production logs found for the selected date.")
            self._clear_display()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load log:\n{str(e)}")
            self._clear_display()

    def _on_date_changed(self):
        """Handle date picker change"""
        # Update selected_date based on logging mode
        if self.logging_mode == "daily":
            self.selected_date = self.date_picker.date()
        elif self.logging_mode == "monthly":
            month = self.month_combo.currentIndex() + 1
            year = int(self.year_combo.currentText())
            self.selected_date = (month, year)
        else:  # yearly
            self.selected_date = int(self.year_combo.currentText())

        # Reload log for new date
        self._load_and_display_log()

    def _on_refresh_clicked(self):
        """Handle refresh button click"""
        self._load_and_display_log()

    def _on_export_clicked(self):
        """Export currently displayed logs to CSV"""
        if self.log_table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "No log data to export.")
            return

        # Default filename
        default_name = self._get_export_filename()

        # Ask for save location
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Production Log",
            str(Path.home() / default_name),
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        # Export
        success = self._export_to_csv(file_path)

        if success:
            QMessageBox.information(self, "Export Successful",
                f"Production log exported to:\n{file_path}")
        else:
            QMessageBox.critical(self, "Export Failed",
                "Failed to export production log.")

    def _export_to_csv(self, save_path: str) -> bool:
        """Export current table data to CSV file"""
        try:
            with open(save_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write headers
                headers = ['Timestamp', 'Server', 'Filename', 'Pages', 'Copies', 'Total_Prints', 'Mode']
                writer.writerow(headers)

                # Write data rows
                for row in range(self.log_table.rowCount()):
                    row_data = [
                        self.log_table.item(row, col).text()
                        for col in range(self.log_table.columnCount())
                    ]
                    writer.writerow(row_data)

            return True

        except Exception as e:
            print(f"Error exporting to CSV: {e}")
            return False

    def _get_export_filename(self) -> str:
        """Generate default export filename"""
        if self.logging_mode == "daily":
            date_str = self.selected_date.toString("yyyy-MM-dd")
            return f"production_log_{date_str}.csv"
        elif self.logging_mode == "monthly":
            month, year = self.selected_date
            return f"production_log_{year}-{month:02d}.csv"
        else:
            return f"production_log_{self.selected_date}.csv"
