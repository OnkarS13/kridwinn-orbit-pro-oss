"""
Activation Dialog
GUI for importing and activating .lic license files.
First-time activation requires internet for Firebase registration.
"""

from typing import Optional
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QSizePolicy, QFileDialog, QProgressBar
)

from .license_client import LicenseClient


class ActivationWorker(QObject):
    """Background worker for license activation (involves network call)"""
    finished = Signal(bool, str)

    def __init__(self, client: LicenseClient, file_path: str):
        super().__init__()
        self.client = client
        self.file_path = file_path

    def run(self):
        try:
            success, message = self.client.import_license_file(self.file_path)
            self.finished.emit(success, message)
        except Exception as e:
            self.finished.emit(False, f"Activation error: {str(e)}")


class ActivationDialog(QDialog):
    """
    License activation dialog.
    Shows machine ID and allows importing a .lic license file.
    """

    def __init__(self, license_client: Optional[LicenseClient] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.license_client = license_client or LicenseClient()
        self.selected_file_path = None
        self.activation_thread = None
        self.activation_worker = None

        self._init_ui()

    def _init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("Kridwinn Orbit Pro - License Activation")
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setMinimumHeight(450)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel("License Activation Required")
        title.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "This application requires a valid license to run.\n"
            "Import the license file (.lic) provided by your administrator.\n"
            "Internet connection is required for first-time activation."
        )
        desc.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Machine ID section
        machine_group = QWidget()
        machine_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        machine_layout = QVBoxLayout(machine_group)
        machine_layout.setSpacing(8)

        machine_label = QLabel("Your Machine ID:")
        machine_label.setStyleSheet("font-weight: bold; color: #34495e;")
        machine_layout.addWidget(machine_label)

        self.machine_id_display = QLineEdit()
        self.machine_id_display.setText(self.license_client.get_machine_id())
        self.machine_id_display.setReadOnly(True)
        self.machine_id_display.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border: 2px solid #3498db;
                border-radius: 5px;
                background-color: #ecf0f1;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        machine_layout.addWidget(self.machine_id_display)

        copy_btn = QPushButton("Copy Machine ID")
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        copy_btn.clicked.connect(self._copy_machine_id)
        machine_layout.addWidget(copy_btn)

        layout.addWidget(machine_group)

        # License file import section
        file_group = QWidget()
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(8)

        file_label = QLabel("License File:")
        file_label.setStyleSheet("font-weight: bold; color: #34495e;")
        file_layout.addWidget(file_label)

        # File path display + browse button
        file_row = QHBoxLayout()
        file_row.setSpacing(8)

        self.file_path_display = QLineEdit()
        self.file_path_display.setPlaceholderText("No file selected...")
        self.file_path_display.setReadOnly(True)
        self.file_path_display.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                background-color: #f8f9fa;
                font-size: 13px;
                color: #2c3e50;
            }
        """)
        file_row.addWidget(self.file_path_display)

        browse_btn = QPushButton("Browse...")
        browse_btn.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6d28d9;
            }
        """)
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)

        file_layout.addLayout(file_row)
        layout.addWidget(file_group)

        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                text-align: center;
                background-color: #ecf0f1;
            }
            QProgressBar::chunk {
                background-color: #7c3aed;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Status message
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #000000; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(30)
        layout.addWidget(self.status_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        self.activate_btn = QPushButton("Activate License")
        self.activate_btn.setEnabled(False)
        self.activate_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 12px 25px;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.activate_btn.clicked.connect(self._activate_license)
        button_layout.addWidget(self.activate_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 12px 25px;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # Help text
        help_text = QLabel(
            "Need a license? Contact your administrator.\n"
            "Provide them with your Machine ID shown above."
        )
        help_text.setStyleSheet("color: #95a5a6; font-size: 11px; font-style: italic;")
        help_text.setAlignment(Qt.AlignCenter)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        layout.addStretch()

    def _copy_machine_id(self):
        """Copy machine ID to clipboard"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.machine_id_display.text())
        self.status_label.setText("Machine ID copied to clipboard!")
        self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")

    def _browse_file(self):
        """Open file dialog to select .lic file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select License File",
            "",
            "License Files (*.lic);;All Files (*.*)"
        )
        if file_path:
            self.selected_file_path = file_path
            self.file_path_display.setText(file_path)
            self.activate_btn.setEnabled(True)
            self.status_label.setText("")

    def _activate_license(self):
        """Start license activation in background thread"""
        if not self.selected_file_path:
            self.status_label.setText("Please select a license file first.")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
            return

        # Disable controls during activation
        self.activate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Verifying and registering license...")
        self.status_label.setStyleSheet("color: #3498db; font-weight: bold;")

        # Run in background thread (involves network call to Firebase)
        self.activation_thread = QThread()
        self.activation_worker = ActivationWorker(self.license_client, self.selected_file_path)
        self.activation_worker.moveToThread(self.activation_thread)

        self.activation_thread.started.connect(self.activation_worker.run)
        self.activation_worker.finished.connect(self._on_activation_finished)
        self.activation_worker.finished.connect(self.activation_thread.quit)
        self.activation_worker.finished.connect(self.activation_worker.deleteLater)
        self.activation_thread.finished.connect(self.activation_thread.deleteLater)

        self.activation_thread.start()

    def _on_activation_finished(self, success: bool, message: str):
        """Handle activation completion"""
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        if success:
            self.status_label.setText("License activated successfully!")
            self.status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            QTimer.singleShot(1000, self.accept)
        else:
            self.activate_btn.setEnabled(True)
            self.status_label.setText(f"Activation failed: {message}")
            self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def closeEvent(self, event):
        """Ensure thread cleanup on close"""
        if self.activation_thread and self.activation_thread.isRunning():
            self.activation_thread.quit()
            self.activation_thread.wait(2000)
        event.accept()
