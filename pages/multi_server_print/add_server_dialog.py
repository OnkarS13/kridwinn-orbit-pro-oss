"""
Add Server Dialog - Dialog for adding new printer servers
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QMessageBox
)


class AddServerDialog(QDialog):
    """Dialog for adding a new printer server"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Printer Server")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._init_ui()
    
    def _init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        
        # Title
        title = QLabel("<h3>Add New Printer Server</h3>")
        layout.addWidget(title)
        
        # Form layout
        form = QFormLayout()
        form.setSpacing(15)
        
        # Server name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Production Printer")
        form.addRow("Server Name:", self.name_edit)
        
        # IP address
        self.ip_edit = QLineEdit()
        self.ip_edit.setText("localhost")
        self.ip_edit.setPlaceholderText("e.g., 192.168.1.100 or localhost")
        form.addRow("IP Address:", self.ip_edit)
        
        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(2000)
        form.addRow("Port:", self.port_spin)
        
        layout.addLayout(form)
        
        # Info label
        info = QLabel("ℹ️ Make sure the GIS Print Server is running at this address.")
        info.setStyleSheet("color: #666; font-style: italic; padding: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setObjectName("SecondaryButton")
        
        add_btn = QPushButton("Add Server")
        add_btn.clicked.connect(self._validate_and_accept)
        add_btn.setDefault(True)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(add_btn)
        layout.addLayout(button_layout)
        
        # Apply styling
        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
            }
            QLabel {
                color: #212529;
            }
            QLineEdit, QSpinBox {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px;
                color: #212529;
            }
            QLineEdit:focus, QSpinBox:focus {
                border-color: #80bdff;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton#SecondaryButton {
                background-color: #6c757d;
            }
            QPushButton#SecondaryButton:hover {
                background-color: #5a6268;
            }
        """)
    
    def _validate_and_accept(self):
        """Validate inputs before accepting"""
        name = self.name_edit.text().strip()
        ip = self.ip_edit.text().strip()
        
        if not name:
            QMessageBox.warning(self, "Validation Error", "Please enter a server name.")
            self.name_edit.setFocus()
            return
        
        if not ip:
            QMessageBox.warning(self, "Validation Error", "Please enter an IP address.")
            self.ip_edit.setFocus()
            return
        
        self.accept()
    
    def get_values(self):
        """Get the entered values"""
        return {
            'name': self.name_edit.text().strip(),
            'ip': self.ip_edit.text().strip(),
            'port': self.port_spin.value()
        }

