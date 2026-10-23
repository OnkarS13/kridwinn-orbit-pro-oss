"""
Print Server Configuration Section
Centralized management UI for GIS Print Server connections
"""

import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox, QSpinBox,
    QCheckBox, QScrollArea
)
from PySide6.QtGui import QColor

# Import server management from multi_server_print module
from pages.multi_server_print.server_manager import PrintServerManager
from pages.multi_server_print.add_server_dialog import AddServerDialog
from pages.multi_server_print.edit_server_dialog import EditServerDialog


class PrintServerConfigSection(QWidget):
    """
    Centralized Print Server Configuration Section
    Manages GIS Print Server connections for the entire application
    """
    
    server_list_changed = Signal()  # Emit when servers are added/removed/edited
    
    def __init__(self, parent=None, multi_server_section=None):
        super().__init__(parent)
        
        # Use the same server manager as multi_server_print
        self.server_manager = PrintServerManager()
        self.multi_server_section = multi_server_section  # Reference to multi-server section for auto-refresh
        
        self._init_ui()
        self._load_servers()
    
    def _style_group_box(self, group_box):
        """Apply custom styling to group boxes"""
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
        """Initialize the UI - full horizontal layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        # Title section
        title_label = QLabel("🖨️ GIS Print Server Configuration")
        title_label.setStyleSheet("font-size: 20pt; font-weight: bold; color: #212529; padding: 10px;")
        main_layout.addWidget(title_label)
        
        
        # Main content area - full width
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setSpacing(20)
        
        # Left side: Server List (40% width)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Server list group
        server_list_group = QGroupBox("Print Servers")
        self._style_group_box(server_list_group)
        server_list_layout = QVBoxLayout()
        
        self.server_list_widget = QListWidget()
        self.server_list_widget.setMinimumHeight(300)
        self.server_list_widget.currentRowChanged.connect(self._on_server_selected)
        
        # Add selection highlighting styles
        self.server_list_widget.setStyleSheet("""
            QListWidget {
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item {
                background-color: transparent;
                border: none;
                padding: 2px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #007bff;
                color: white;
                border-radius: 4px;
            }
            QListWidget::item:hover {
                background-color: #e3f2fd;
                border-radius: 4px;
            }
            QListWidget::item:selected:hover {
                background-color: #0056b3;
            }
        """)
        
        server_list_layout.addWidget(self.server_list_widget)
        
        # Action buttons
        button_layout = QHBoxLayout()
        self.add_server_btn = QPushButton("➕ Add Server")
        self.add_server_btn.clicked.connect(self._add_server)
        self.edit_server_btn = QPushButton("✎ Edit Server")
        self.edit_server_btn.clicked.connect(self._edit_server)
        self.edit_server_btn.setEnabled(False)
        self.remove_server_btn = QPushButton("➖ Remove Server")
        self.remove_server_btn.clicked.connect(self._remove_server)
        self.remove_server_btn.setEnabled(False)
        
        button_layout.addWidget(self.add_server_btn)
        button_layout.addWidget(self.edit_server_btn)
        button_layout.addWidget(self.remove_server_btn)
        server_list_layout.addLayout(button_layout)
        
        server_list_group.setLayout(server_list_layout)
        left_layout.addWidget(server_list_group)
        
        content_layout.addWidget(left_widget, 3)  # 30% width
        
        # Right side: Server Details (60% width)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Server details group
        details_group = QGroupBox("Server Details")
        self._style_group_box(details_group)
        details_layout = QVBoxLayout()
        details_layout.setSpacing(15)
        
        # Server ID (read-only)
        id_row = QHBoxLayout()
        id_row.addWidget(QLabel("Server ID:"))
        self.server_id_label = QLabel("--")
        self.server_id_label.setStyleSheet("font-weight: bold; color: #6c757d; font-family: monospace;")
        id_row.addWidget(self.server_id_label)
        id_row.addStretch()
        details_layout.addLayout(id_row)
        
        # Server Name
        name_row = QHBoxLayout()
        name_label = QLabel("Name:")
        name_label.setMinimumWidth(100)
        name_row.addWidget(name_label)
        self.server_name_edit = QLineEdit()
        self.server_name_edit.setPlaceholderText("Enter server name...")
        self.server_name_edit.setEnabled(False)
        name_row.addWidget(self.server_name_edit, 1)  # Expand to fill space
        details_layout.addLayout(name_row)
        
        # IP Address
        ip_row = QHBoxLayout()
        ip_label = QLabel("IP Address:")
        ip_label.setMinimumWidth(100)
        ip_row.addWidget(ip_label)
        self.server_ip_edit = QLineEdit()
        self.server_ip_edit.setPlaceholderText("e.g., localhost or 192.168.1.100")
        self.server_ip_edit.setEnabled(False)
        ip_row.addWidget(self.server_ip_edit, 1)  # Expand to fill space
        details_layout.addLayout(ip_row)
        
        # Port
        port_row = QHBoxLayout()
        port_label = QLabel("Port:")
        port_label.setMinimumWidth(100)
        port_row.addWidget(port_label)
        self.server_port_spin = QSpinBox()
        self.server_port_spin.setRange(1, 65535)
        self.server_port_spin.setValue(2000)
        self.server_port_spin.setEnabled(False)
        self.server_port_spin.setMinimumWidth(120)
        port_row.addWidget(self.server_port_spin)
        port_row.addStretch()
        details_layout.addLayout(port_row)
        
        # Enabled checkbox
        enabled_row = QHBoxLayout()
        self.server_enabled_checkbox = QCheckBox("Server Enabled")
        self.server_enabled_checkbox.setChecked(True)
        self.server_enabled_checkbox.setEnabled(False)
        enabled_row.addWidget(self.server_enabled_checkbox)
        enabled_row.addStretch()
        details_layout.addLayout(enabled_row)
        
        # Connection status
        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self.connection_status_label = QLabel("Not connected")
        self.connection_status_label.setStyleSheet("font-weight: bold; color: #dc3545;")
        self.test_connection_btn = QPushButton("Test Connection")
        self.test_connection_btn.clicked.connect(self._test_connection)
        self.test_connection_btn.setEnabled(False)
        status_row.addWidget(self.connection_status_label)
        status_row.addStretch()
        status_row.addWidget(self.test_connection_btn)
        details_layout.addLayout(status_row)
        
        # Connection management buttons
        connection_buttons_row = QHBoxLayout()
        connection_buttons_row.addWidget(QLabel("Connection:"))
        
        self.connect_btn = QPushButton("🔗 Connect")
        self.connect_btn.clicked.connect(self._connect_server)
        self.connect_btn.setEnabled(False)
        self.connect_btn.setStyleSheet("""
            QPushButton { background-color: #28a745; color: white; font-weight: bold; padding: 8px 15px; }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #c3e6cb; }
        """)
        
        self.reconnect_btn = QPushButton("🔄 Reconnect")
        self.reconnect_btn.clicked.connect(self._reconnect_server)
        self.reconnect_btn.setEnabled(False)
        self.reconnect_btn.setStyleSheet("""
            QPushButton { background-color: #ffc107; color: #212529; font-weight: bold; padding: 8px 15px; }
            QPushButton:hover { background-color: #e0a800; }
            QPushButton:disabled { background-color: #fff3cd; }
        """)
        
        self.disconnect_btn = QPushButton("❌ Disconnect")
        self.disconnect_btn.clicked.connect(self._disconnect_server)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet("""
            QPushButton { background-color: #dc3545; color: white; font-weight: bold; padding: 8px 15px; }
            QPushButton:hover { background-color: #c82333; }
            QPushButton:disabled { background-color: #f5c6cb; }
        """)
        
        connection_buttons_row.addWidget(self.connect_btn)
        connection_buttons_row.addWidget(self.reconnect_btn)
        connection_buttons_row.addWidget(self.disconnect_btn)
        connection_buttons_row.addStretch()
        details_layout.addLayout(connection_buttons_row)
        
        # Save button
        details_layout.addSpacing(20)
        save_row = QHBoxLayout()
        self.save_changes_btn = QPushButton("💾 Save Changes")
        self.save_changes_btn.clicked.connect(self._save_server_changes)
        self.save_changes_btn.setEnabled(False)
        self.save_changes_btn.setStyleSheet("""
            QPushButton { background-color: #28a745; color: white; font-weight: bold; padding: 10px 20px; font-size: 11pt; }
            QPushButton:hover { background-color: #218838; }
            QPushButton:disabled { background-color: #c3e6cb; }
        """)
        save_row.addWidget(self.save_changes_btn)
        save_row.addStretch()
        details_layout.addLayout(save_row)
        
        details_layout.addStretch()
        
        details_group.setLayout(details_layout)
        right_layout.addWidget(details_group)
        
        
        content_layout.addWidget(right_widget, 7)  # 70% width
        
        main_layout.addWidget(content_widget, 1)
        
        # Track current selection
        self.current_server_id = None
        
        # Enable change tracking
        self.server_name_edit.textChanged.connect(self._enable_save_button)
        self.server_ip_edit.textChanged.connect(self._enable_save_button)
        self.server_port_spin.valueChanged.connect(self._enable_save_button)
        self.server_enabled_checkbox.toggled.connect(self._enable_save_button)
    
    def _load_servers(self):
        """Load servers from manager and populate list"""
        self.server_list_widget.clear()
        servers = self.server_manager.get_all_servers()
        
        for server_id, config in servers.items():
            item = QListWidgetItem()
            
            # Create custom widget for list item
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(8, 4, 8, 4)
            
            # Status indicator (green/red dot)
            status_label = QLabel("●")
            if config.enabled:
                status_label.setStyleSheet("color: #28a745; font-size: 16pt;")
            else:
                status_label.setStyleSheet("color: #dc3545; font-size: 16pt;")
            
            # Server info
            name_label = QLabel(f"{config.name}")
            name_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: inherit;")
            
            ip_port_label = QLabel(f"{config.ip}:{config.port}")
            ip_port_label.setStyleSheet("color: #6c757d; font-size: 10pt;")
            
            layout.addWidget(status_label)
            layout.addWidget(name_label, 1)
            layout.addWidget(ip_port_label)
            widget.setLayout(layout)
            
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, server_id)  # Store server ID
            
            self.server_list_widget.addItem(item)
            self.server_list_widget.setItemWidget(item, widget)
        
        # Select first server if any
        if self.server_list_widget.count() > 0:
            self.server_list_widget.setCurrentRow(0)
    
    def _on_server_selected(self, row):
        """Handle server selection"""
        if row < 0:
            self._clear_details()
            return
        
        item = self.server_list_widget.item(row)
        if not item:
            return
        
        server_id = item.data(Qt.UserRole)
        config = self.server_manager.get_server(server_id)
        
        if not config:
            return
        
        self.current_server_id = server_id
        
        # Populate details
        self.server_id_label.setText(server_id[:8] + "...")  # Show first 8 chars
        self.server_name_edit.setText(config.name)
        self.server_ip_edit.setText(config.ip)
        self.server_port_spin.setValue(config.port)
        self.server_enabled_checkbox.setChecked(config.enabled)
        
        # Enable editing
        self.server_name_edit.setEnabled(True)
        self.server_ip_edit.setEnabled(True)
        self.server_port_spin.setEnabled(True)
        self.server_enabled_checkbox.setEnabled(True)
        self.test_connection_btn.setEnabled(True)
        
        # Enable connection management buttons
        self.connect_btn.setEnabled(True)
        self.reconnect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(True)
        
        # Enable edit/remove buttons
        self.edit_server_btn.setEnabled(True)
        self.remove_server_btn.setEnabled(True)
        
        # Disable save initially (enable on change)
        self.save_changes_btn.setEnabled(False)
        
        # Update connection status
        self.connection_status_label.setText("Not tested")
        self.connection_status_label.setStyleSheet("font-weight: bold; color: #6c757d;")
        
        # Initialize connection state
        self._update_connection_buttons_state(False)
    
    def _clear_details(self):
        """Clear details panel"""
        self.current_server_id = None
        self.server_id_label.setText("--")
        self.server_name_edit.clear()
        self.server_name_edit.setEnabled(False)
        self.server_ip_edit.clear()
        self.server_ip_edit.setEnabled(False)
        self.server_port_spin.setValue(2000)
        self.server_port_spin.setEnabled(False)
        self.server_enabled_checkbox.setChecked(True)
        self.server_enabled_checkbox.setEnabled(False)
        self.test_connection_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.reconnect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        self.edit_server_btn.setEnabled(False)
        self.remove_server_btn.setEnabled(False)
        self.save_changes_btn.setEnabled(False)
        self.connection_status_label.setText("No server selected")
        self.connection_status_label.setStyleSheet("font-weight: bold; color: #6c757d;")
    
    def _enable_save_button(self):
        """Enable save button when changes are made"""
        if self.current_server_id:
            self.save_changes_btn.setEnabled(True)
    
    def _add_server(self):
        """Show dialog to add new server"""
        dialog = AddServerDialog(self)
        if dialog.exec():
            values = dialog.get_values()
            try:
                server_id = self.server_manager.add_server(
                    values['name'],
                    values['ip'],
                    values['port']
                )
            except ValueError as e:
                QMessageBox.warning(self, "Duplicate Server", str(e))
                return
            except Exception as e:
                QMessageBox.critical(self, "Add Server Failed", str(e))
                return
            self._load_servers()
            self.server_list_changed.emit()
            
            # Auto-refresh multi-server section if available
            if self.multi_server_section:
                self.multi_server_section.refresh_servers_external()
            
            # Show success message
            QMessageBox.information(
                self, "Server Added",
                f"Server '{values['name']}' has been added successfully!"
            )
    
    def _edit_server(self):
        """Show dialog to edit current server"""
        if not self.current_server_id:
            return
        
        config = self.server_manager.get_server(self.current_server_id)
        if not config:
            return
        
        dialog = EditServerDialog(config.name, config.ip, config.port, self)
        if dialog.exec():
            server_data = dialog.get_server_data()
            # Update via manager (validates duplicates)
            ok = self.server_manager.update_server(
                self.current_server_id,
                name=server_data['name'],
                ip=server_data['ip'],
                port=server_data['port']
            )
            if not ok:
                QMessageBox.warning(self, "Update Failed", "Another server already uses this IP/Port or Port is in use.")
                return
            self._load_servers()
            self.server_list_changed.emit()
            
            # Auto-refresh multi-server section if available
            if self.multi_server_section:
                self.multi_server_section.refresh_servers_external()
            
            # Reselect the edited server
            for i in range(self.server_list_widget.count()):
                item = self.server_list_widget.item(i)
                if item.data(Qt.UserRole) == self.current_server_id:
                    self.server_list_widget.setCurrentRow(i)
                    break
            
            QMessageBox.information(
                self, "Server Updated",
                f"Server '{config.name}' has been updated successfully!"
            )
    
    def _remove_server(self):
        """Remove current server"""
        if not self.current_server_id:
            return
        
        config = self.server_manager.get_server(self.current_server_id)
        if not config:
            return
        
        # Confirm removal
        reply = QMessageBox.question(
            self,
            'Remove Server',
            f'Are you sure you want to remove server "{config.name}"?\n\n'
            f'IP: {config.ip}:{config.port}\n\n'
            'This will affect all sections using this server.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.server_manager.remove_server(self.current_server_id)
            self._load_servers()
            self.server_list_changed.emit()
            
            # Auto-refresh multi-server section if available
            if self.multi_server_section:
                self.multi_server_section.refresh_servers_external()
            
            QMessageBox.information(
                self, "Server Removed",
                f"Server '{config.name}' has been removed successfully!"
            )
    
    def _save_server_changes(self):
        """Save changes to current server"""
        if not self.current_server_id:
            return
        
        config = self.server_manager.get_server(self.current_server_id)
        if not config:
            return
        
        # Update config with form values
        config.name = self.server_name_edit.text().strip()
        config.ip = self.server_ip_edit.text().strip()
        config.port = self.server_port_spin.value()
        config.enabled = self.server_enabled_checkbox.isChecked()
        
        # Validate
        if not config.name:
            QMessageBox.warning(self, "Invalid Name", "Server name cannot be empty!")
            return
        
        if not config.ip:
            QMessageBox.warning(self, "Invalid IP", "IP address cannot be empty!")
            return
        
        # Save via manager (validates duplicates)
        ok = self.server_manager.update_server(
            self.current_server_id,
            name=config.name,
            ip=config.ip,
            port=config.port,
            enabled=config.enabled,
        )
        if not ok:
            QMessageBox.warning(self, "Save Failed", "Another server already uses this IP/Port or Port is in use.")
            return
        self._load_servers()
        self.server_list_changed.emit()
        
        # Auto-refresh multi-server section if available
        if self.multi_server_section:
            self.multi_server_section.refresh_servers_external()
        
        # Reselect the edited server
        for i in range(self.server_list_widget.count()):
            item = self.server_list_widget.item(i)
            if item.data(Qt.UserRole) == self.current_server_id:
                self.server_list_widget.setCurrentRow(i)
                break
        
        self.save_changes_btn.setEnabled(False)
        
        QMessageBox.information(
            self, "Changes Saved",
            f"Server '{config.name}' has been updated successfully!"
        )
    
    def _test_connection(self):
        """Test connection to current server"""
        if not self.current_server_id:
            return
        
        config = self.server_manager.get_server(self.current_server_id)
        if not config:
            return
        
        # Update status to testing
        self.connection_status_label.setText("Testing...")
        self.connection_status_label.setStyleSheet("font-weight: bold; color: #ff6600;")
        self.test_connection_btn.setEnabled(False)
        
        # Test connection in background
        from PySide6.QtCore import QThread, QObject
        import socket
        
        class ConnectionTester(QObject):
            finished = Signal(bool, str)
            
            def __init__(self, host, port):
                super().__init__()
                self.host = host
                self.port = port
            
            def run(self):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)
                    sock.connect((self.host, self.port))
                    
                    # Try to receive connection message
                    response = b""
                    while b'\n' not in response:
                        chunk = sock.recv(1024)
                        if not chunk:
                            break
                        response += chunk
                    
                    sock.close()
                    
                    if b'N,C' in response or b'N,A' in response:
                        self.finished.emit(True, "Connected successfully")
                    else:
                        self.finished.emit(False, f"Unexpected response: {response.decode()[:50]}")
                        
                except socket.timeout:
                    self.finished.emit(False, "Connection timeout")
                except ConnectionRefusedError:
                    self.finished.emit(False, "Connection refused - server not running")
                except Exception as e:
                    self.finished.emit(False, f"Error: {str(e)}")
        
        # Create thread
        self.test_thread = QThread()
        self.test_worker = ConnectionTester(config.ip, config.port)
        self.test_worker.moveToThread(self.test_thread)
        
        self.test_thread.started.connect(self.test_worker.run)
        self.test_worker.finished.connect(self.test_thread.quit)
        self.test_worker.finished.connect(self.test_worker.deleteLater)
        self.test_thread.finished.connect(self.test_thread.deleteLater)
        self.test_worker.finished.connect(self._on_connection_test_result)
        
        self.test_thread.start()
    
    def _on_connection_test_result(self, success, message):
        """Handle connection test result"""
        if success:
            self.connection_status_label.setText("✅ Connected")
            self.connection_status_label.setStyleSheet("font-weight: bold; color: #28a745;")
        else:
            self.connection_status_label.setText(f"❌ {message}")
            self.connection_status_label.setStyleSheet("font-weight: bold; color: #dc3545;")
        
        self.test_connection_btn.setEnabled(True)
    
    def refresh_servers(self):
        """Public method to refresh server list (called from other sections)"""
        self._load_servers()
    
    def _update_connection_buttons_state(self, is_connected):
        """Update connection buttons state based on connection status"""
        if is_connected:
            self.connect_btn.setEnabled(False)
            self.reconnect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(True)
        else:
            self.connect_btn.setEnabled(True)
            self.reconnect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(False)
    
    def _connect_server(self):
        """Connect to the selected server"""
        if not self.current_server_id:
            return
        
        config = self.server_manager.get_server(self.current_server_id)
        if not config:
            return
        
        # Update status to connecting
        self.connection_status_label.setText("🔄 Connecting...")
        self.connection_status_label.setStyleSheet("font-weight: bold; color: #ff6600;")
        self._update_connection_buttons_state(False)
        
        # Disable all connection buttons during connection
        self.connect_btn.setEnabled(False)
        self.reconnect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(False)
        
        # Perform connection in background thread
        self._perform_connection_test(config.ip, config.port, is_connect=True)
    
    def _reconnect_server(self):
        """Reconnect to the selected server"""
        if not self.current_server_id:
            return
        
        # First disconnect, then connect
        self._disconnect_server()
        # Small delay before reconnecting
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1000, self._connect_server)
    
    def _disconnect_server(self):
        """Disconnect from the selected server"""
        if not self.current_server_id:
            return
        
        config = self.server_manager.get_server(self.current_server_id)
        if not config:
            return
        
        # Update status to disconnected
        self.connection_status_label.setText("❌ Disconnected")
        self.connection_status_label.setStyleSheet("font-weight: bold; color: #dc3545;")
        
        # Update button states
        self._update_connection_buttons_state(False)
        
        # Show disconnect message
        QMessageBox.information(
            self, "Disconnected",
            f"Disconnected from server '{config.name}' at {config.ip}:{config.port}"
        )
    
    def _perform_connection_test(self, host, port, is_connect=False):
        """Perform connection test or actual connection"""
        from PySide6.QtCore import QThread, QObject
        import socket
        
        class ConnectionWorker(QObject):
            finished = Signal(bool, str)
            
            def __init__(self, host, port, is_connect):
                super().__init__()
                self.host = host
                self.port = port
                self.is_connect = is_connect
            
            def run(self):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)  # Longer timeout for connection
                    sock.connect((self.host, self.port))
                    
                    # Try to receive connection message
                    response = b""
                    while b'\n' not in response:
                        chunk = sock.recv(1024)
                        if not chunk:
                            break
                        response += chunk
                    
                    sock.close()
                    
                    if b'N,C' in response or b'N,A' in response:
                        if self.is_connect:
                            self.finished.emit(True, "Successfully connected")
                        else:
                            self.finished.emit(True, "Connected successfully")
                    else:
                        self.finished.emit(False, f"Unexpected response: {response.decode()[:50]}")
                        
                except socket.timeout:
                    self.finished.emit(False, "Connection timeout")
                except ConnectionRefusedError:
                    self.finished.emit(False, "Connection refused - server not running")
                except Exception as e:
                    self.finished.emit(False, f"Error: {str(e)}")
        
        # Create thread
        self.connection_thread = QThread()
        self.connection_worker = ConnectionWorker(host, port, is_connect)
        self.connection_worker.moveToThread(self.connection_thread)
        
        self.connection_thread.started.connect(self.connection_worker.run)
        self.connection_worker.finished.connect(self.connection_thread.quit)
        self.connection_worker.finished.connect(self.connection_worker.deleteLater)
        self.connection_thread.finished.connect(self.connection_thread.deleteLater)
        
        if is_connect:
            self.connection_worker.finished.connect(self._on_connection_result)
        else:
            self.connection_worker.finished.connect(self._on_connection_test_result)
        
        self.connection_thread.start()
    
    def _on_connection_result(self, success, message):
        """Handle connection result (for Connect button)"""
        if success:
            self.connection_status_label.setText("✅ Connected")
            self.connection_status_label.setStyleSheet("font-weight: bold; color: #28a745;")
            self._update_connection_buttons_state(True)
            QMessageBox.information(
                self, "Connected",
                f"Successfully connected to server!\n\n{message}"
            )
        else:
            self.connection_status_label.setText(f"❌ {message}")
            self.connection_status_label.setStyleSheet("font-weight: bold; color: #dc3545;")
            self._update_connection_buttons_state(False)
            QMessageBox.warning(
                self, "Connection Failed",
                f"Failed to connect to server:\n\n{message}"
            )
        
        # Re-enable test connection button
        self.test_connection_btn.setEnabled(True)

