"""
Edit Server Dialog (shared)
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QPushButton, QMessageBox
from PySide6.QtCore import Qt


class EditServerDialog(QDialog):
    """Dialog for editing existing printer server configuration"""

    def __init__(self, server_name, server_ip, server_port, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Print Server")
        self.setMinimumWidth(300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._init_ui()
        self.name_edit.setText(server_name); self.ip_edit.setText(server_ip); self.port_spin.setValue(server_port)

    def _init_ui(self):
        main_layout = QVBoxLayout(self); main_layout.setSpacing(10)
        name_layout = QHBoxLayout(); name_layout.addWidget(QLabel("Server Name:"))
        self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("Enter server name"); name_layout.addWidget(self.name_edit); main_layout.addLayout(name_layout)
        ip_layout = QHBoxLayout(); ip_layout.addWidget(QLabel("IP Address:"))
        self.ip_edit = QLineEdit(); self.ip_edit.setPlaceholderText("Enter IP address"); ip_layout.addWidget(self.ip_edit); main_layout.addLayout(ip_layout)
        port_layout = QHBoxLayout(); port_layout.addWidget(QLabel("Port:"))
        self.port_spin = QSpinBox(); self.port_spin.setRange(1024, 65535); self.port_spin.setValue(2000); port_layout.addWidget(self.port_spin); main_layout.addLayout(port_layout)
        button_layout = QHBoxLayout(); apply_button = QPushButton("Apply Changes"); apply_button.clicked.connect(self.accept)
        cancel_button = QPushButton("Cancel"); cancel_button.clicked.connect(self.reject)
        button_layout.addStretch(); button_layout.addWidget(apply_button); button_layout.addWidget(cancel_button); main_layout.addLayout(button_layout)

    def accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Input Error", "Server Name cannot be empty."); return
        if not self.ip_edit.text().strip():
            QMessageBox.warning(self, "Input Error", "IP Address cannot be empty."); return
        ip = self.ip_edit.text().strip()
        if not self._is_valid_ip(ip):
            QMessageBox.warning(self, "Input Error", "Please enter a valid IP address."); return
        super().accept()

    def _is_valid_ip(self, ip):
        ip = ip.strip().lower()
        if ip == 'localhost':
            return True
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            for part in parts:
                num = int(part)
                if num < 0 or num > 255:
                    return False
            return True
        except ValueError:
            return False

    def get_server_data(self):
        return { 'name': self.name_edit.text().strip(), 'ip': self.ip_edit.text().strip(), 'port': self.port_spin.value() }


