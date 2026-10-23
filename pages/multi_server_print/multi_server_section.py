"""
Multi-Server Print Section - Main widget for managing multiple print servers
"""
import logging
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QStackedWidget, QMessageBox, QLabel, QDialog
)
from .shared.server_manager import PrintServerManager
from .shared.server_config import PrinterServerConfig
from .shared.add_server_dialog import AddServerDialog
from .shared.edit_server_dialog import EditServerDialog
from .server_control_widget import ServerControlWidget
from .multi_server_worker import MultiServerPrintWorker
from .mode_selector.mode_selector_widget import ModeSelectorWidget
from .rip2print.rip2print_section import RIP2PrintSection
from .img2print.img2print_placeholder import IMG2PrintPlaceholder
from .pdf2print.pdf2print_placeholder import PDF2PrintPlaceholder

logger = logging.getLogger(__name__)


class MultiServerPrintSection(QWidget):
    """Main section for managing multiple print servers"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = PrintServerManager()
        self.server_widgets = {}  # {server_id: ServerControlWidget}
        self.workers = {}  # {server_id: MultiServerPrintWorker}
        self.threads = {}  # {server_id: QThread}
        
        self._init_ui()
        self._load_servers()
    
    def _init_ui(self):
        """Initialize UI components"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # LEFT PANEL: Server List (hidden on main menu)
        left_panel = self._create_left_panel()
        self.left_panel = left_panel
        layout.addWidget(left_panel, 0)  # Fixed width for left panel
        
        # RIGHT PANEL: content stack with a centered menu page
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Content stack - page 0: MENU, subsequent pages: modes and legacy
        self.server_stack = QStackedWidget()  # existing server control stack
        self.content_stack = QStackedWidget()  # new top-level content stack
        # MENU page (large centered buttons)
        self.mode_selector = ModeSelectorWidget()
        menu_page = QWidget()
        _ml = QVBoxLayout(menu_page)
        _ml.setContentsMargins(0, 30, 0, 0)
        _ml.addWidget(self.mode_selector)
        self.content_stack.addWidget(menu_page)
        # Add RIP2PRINT section as second page
        self.rip2print_section = RIP2PrintSection(self.manager)
        self.content_stack.addWidget(self.rip2print_section)
        # Add IMG/PDF placeholders
        self.img2print_placeholder = IMG2PrintPlaceholder()
        self.pdf2print_placeholder = PDF2PrintPlaceholder()
        self.content_stack.addWidget(self.img2print_placeholder)
        self.content_stack.addWidget(self.pdf2print_placeholder)
        # Add legacy server control stack as a page
        self.content_stack.addWidget(self.server_stack)

        # Default to MENU
        self.content_stack.setCurrentIndex(0)

        right_layout.addWidget(self.content_stack, 1)
        layout.addWidget(right_container, 1)  # Flexible width for right panel

        # Hide left panel on menu
        self.left_panel.setVisible(False)

        # Wire mode selector switching to explicit pages
        def _on_mode_selected(mode: str):
            if mode == "rip2print":
                self._set_left_panel_mode(show_list=True)
                self.content_stack.setCurrentWidget(self.rip2print_section)
            elif mode == "img2print":
                self._set_left_panel_mode(show_list=False)
                self.content_stack.setCurrentWidget(self.img2print_placeholder)
            elif mode == "pdf2print":
                self._set_left_panel_mode(show_list=False)
                self.content_stack.setCurrentWidget(self.pdf2print_placeholder)
            elif mode == "legacy":
                self._set_left_panel_mode(show_list=True)
                # server_stack page is the last one we added
                self.content_stack.setCurrentWidget(self.server_stack)
            else:
                self._go_back_to_menu()

        self.mode_selector.mode_selected.connect(_on_mode_selected)
        # no active state on menu
        self.mode_selector.set_active("")

        # Propagate server list changes to RIP2PRINT widgets
        try:
            self.manager.server_added.connect(lambda _sid: self.rip2print_section.set_server_manager(self.manager))
            self.manager.server_updated.connect(lambda _sid: self.rip2print_section.set_server_manager(self.manager))
            self.manager.server_removed.connect(lambda _sid: self.rip2print_section.set_server_manager(self.manager))
        except Exception:
            pass
        
        # Empty state widget
        empty_widget = QWidget()
        empty_layout = QVBoxLayout(empty_widget)
        empty_layout.addStretch()
        empty_label = QLabel("← Select or add a printer server")
        empty_label.setStyleSheet("color: #999; font-size: 14pt; font-style: italic;")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_label)
        empty_layout.addStretch()
        self.server_stack.addWidget(empty_widget)
        self.empty_widget_index = 0
    
    def _create_left_panel(self):
        """Create left panel with server list and controls"""
        panel = QWidget()
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(350)
        panel.setMinimumHeight(400)  # Ensure enough height for buttons
        panel.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-right: 2px solid #dee2e6;
            }
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Back to main menu button
        self.back_btn = QPushButton("⟵ Back to Menu")
        self.back_btn.setMinimumHeight(32)
        self.back_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #6c757d; /* gray */
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #5a6268; }
            QPushButton:pressed { background-color: #545b62; }
            """
        )
        self.back_btn.clicked.connect(self._go_back_to_menu)
        layout.addWidget(self.back_btn)

        # Title
        title = QLabel("<h3>Printer Servers</h3>")
        layout.addWidget(title)
        
        # Server list
        self.server_list = QListWidget()
        self.server_list.setMinimumHeight(150)
        self.server_list.setMaximumHeight(250)  # Limit height to leave room for buttons
        self.server_list.setStyleSheet("""
            QListWidget {
                background-color: #f8f9fa;
                border: 2px solid #ced4da;
                border-radius: 4px;
                font-size: 11pt;
            }
            QListWidget::item {
                padding: 12px;
                border-bottom: 1px solid #dee2e6;
                min-height: 40px;
            }
            QListWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #e9ecef;
            }
        """)
        self.server_list.itemClicked.connect(self._on_server_selected)
        layout.addWidget(self.server_list)
        
        # Button layout
        btn_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("+ Add")
        self.add_btn.setToolTip("Add new printer server")
        self.add_btn.clicked.connect(self._add_server_dialog)
        self.add_btn.setMinimumHeight(35)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        
        self.edit_btn = QPushButton("✏️ Edit")
        self.edit_btn.setToolTip("Edit selected server")
        self.edit_btn.clicked.connect(self._edit_selected_server)
        self.edit_btn.setMinimumHeight(35)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: #212529;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
            QPushButton:pressed {
                background-color: #d39e00;
            }
        """)
        
        self.remove_btn = QPushButton("− Remove")
        self.remove_btn.setToolTip("Remove selected server")
        self.remove_btn.clicked.connect(self._remove_selected_server)
        self.remove_btn.setMinimumHeight(35)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
        """)
        
        # Hide Add/Edit/Remove buttons - server management only in GIS Server Config section
        # btn_layout.addWidget(self.add_btn)
        # btn_layout.addWidget(self.edit_btn)
        # btn_layout.addWidget(self.remove_btn)
        # layout.addLayout(btn_layout)
        
        # Keep the buttons created but hidden (logic preserved)
        self.add_btn.setVisible(False)
        self.edit_btn.setVisible(False)
        self.remove_btn.setVisible(False)
        
        # Add refresh button
        refresh_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setToolTip("Refresh server list from configuration file")
        self.refresh_btn.clicked.connect(self._refresh_servers)
        self.refresh_btn.setMinimumHeight(35)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12pt;
            }
            QPushButton:hover {
                background-color: #138496;
            }
            QPushButton:pressed {
                background-color: #117a8b;
            }
        """)
        refresh_layout.addWidget(self.refresh_btn)
        refresh_layout.addStretch()
        layout.addLayout(refresh_layout)
        
        # Add some spacing and ensure buttons are visible
        layout.addStretch()
        
        return panel

    def _set_left_panel_mode(self, show_list: bool):
        """Show left panel with back button; optionally hide server list block."""
        self.left_panel.setVisible(True)
        self.server_list.setVisible(show_list)
        self.refresh_btn.setVisible(show_list)
        # Keep title visibility same as list
        # Title is the second widget in layout (after back button)
        try:
            title_widget = self.left_panel.layout().itemAt(1).widget()
            if title_widget:
                title_widget.setVisible(show_list)
        except Exception:
            pass

    def _go_back_to_menu(self):
        """Return to the main menu: hide left panel, show menu page, clear selection state."""
        self.left_panel.setVisible(False)
        self.content_stack.setCurrentIndex(0)
        self.mode_selector.set_active("")
    
    def _load_servers(self):
        """Load and display existing servers"""
        servers = self.manager.get_all_servers()
        for server_id, server in servers.items():
            self._add_server_to_ui(server_id, server)
        
        # Select first server if available
        if self.server_list.count() > 0:
            self.server_list.setCurrentRow(0)
            self._on_server_selected(self.server_list.item(0))
    
    def _add_server_dialog(self):
        """Show dialog to add new server"""
        dialog = AddServerDialog(self)
        if dialog.exec():
            values = dialog.get_values()
            server_id = self.manager.add_server(
                values['name'],
                values['ip'],
                values['port']
            )
            server = self.manager.get_server(server_id)
            self._add_server_to_ui(server_id, server)
            
            # Select the newly added server
            self.server_list.setCurrentRow(self.server_list.count() - 1)
    
    def _add_server_to_ui(self, server_id: str, server: PrinterServerConfig):
        """Add server to UI"""
        # Add to list with status indicator in text
        status_icon = "●" if server.enabled else "●"  # Green or red dot
        status_color = "🟢" if server.enabled else "🔴"  # Use emoji for better visibility
        item = QListWidgetItem(f"{status_color} 📡 {server.name}\n{server.ip}:{server.port}")
        item.setData(Qt.UserRole, server_id)
        self.server_list.addItem(item)
        
        # Create control widget
        control_widget = ServerControlWidget(server_id, server)
        control_widget.start_printing_requested.connect(self._start_printing)
        control_widget.stop_printing_requested.connect(self._stop_printing)
        
        self.server_widgets[server_id] = control_widget
        self.server_stack.addWidget(control_widget)
    
    def _edit_selected_server(self):
        """Edit the currently selected server"""
        current_item = self.server_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a server to edit.")
            return
        
        server_id = current_item.data(Qt.UserRole)
        server = self.manager.get_server(server_id)
        if not server:
            QMessageBox.critical(self, "Error", "Server configuration not found.")
            return
        
        # Open edit dialog with current values
        dialog = EditServerDialog(server.name, server.ip, server.port, self)
        if dialog.exec() == QDialog.Accepted:
            new_data = dialog.get_server_data()
            
            # Update server configuration
            success = self.manager.update_server(
                server_id,
                name=new_data['name'],
                ip=new_data['ip'],
                port=new_data['port']
            )
            
            if success:
                # Refresh the entire server list to show updated status dots
                self._refresh_servers(show_message=False)
                logger.info(f"Updated server: {server.name} -> {new_data['name']}")
                QMessageBox.information(self, "Success", f"Server '{new_data['name']}' updated successfully.")
            else:
                QMessageBox.critical(self, "Error", "Failed to update server configuration.")

    def _remove_selected_server(self):
        """Remove the selected server"""
        current_item = self.server_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection", "Please select a server to remove.")
            return
        
        server_id = current_item.data(Qt.UserRole)
        server = self.manager.get_server(server_id)
        
        # Check if server is currently printing
        if server_id in self.workers:
            QMessageBox.warning(
                self,
                "Server Active",
                f"Cannot remove '{server.name}' while it is printing.\nPlease stop the print job first."
            )
            return
        
        # Confirm removal
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            f"Are you sure you want to remove '{server.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Remove from manager
            self.manager.remove_server(server_id)
            
            # Remove from UI
            row = self.server_list.currentRow()
            self.server_list.takeItem(row)
            
            # Remove widget
            if server_id in self.server_widgets:
                widget = self.server_widgets[server_id]
                self.server_stack.removeWidget(widget)
                widget.deleteLater()
                del self.server_widgets[server_id]
            
            # Switch to empty widget if no servers
            if self.server_list.count() == 0:
                self.server_stack.setCurrentIndex(self.empty_widget_index)
    
    def _on_server_selected(self, item):
        """Handle server selection"""
        if not item:
            return
        
        server_id = item.data(Qt.UserRole)
        if server_id in self.server_widgets:
            widget = self.server_widgets[server_id]
            self.server_stack.setCurrentWidget(widget)
    
    def _start_printing(self, server_id: str):
        """Start printing for a specific server"""
        if server_id in self.workers:
            logger.warning(f"Server {server_id} is already printing")
            return
        
        server = self.manager.get_server(server_id)
        widget = self.server_widgets.get(server_id)
        
        if not widget:
            return
        
        # Validate folder
        if not server.rip_folder or not Path(server.rip_folder).exists():
            QMessageBox.warning(
                self,
                "Invalid Folder",
                "Please select a valid RIP folder containing .bmp files."
            )
            return
        
        # Get page filter from widget
        page_filter = widget.get_page_filter()
        
        # Create worker and thread
        thread = QThread()
        worker = MultiServerPrintWorker(server_id, server, page_filter)
        worker.moveToThread(thread)
        
        # Connect signals
        thread.started.connect(worker.run)
        worker.finished.connect(lambda sid, success: self._on_print_finished(sid, success))
        worker.progress.connect(self._on_print_progress)
        worker.error.connect(self._on_print_error)
        worker.connection_status.connect(self._on_connection_status)
        worker.files_discovered.connect(self._on_files_discovered)
        
        # Store references
        self.workers[server_id] = worker
        self.threads[server_id] = thread
        
        # Update UI
        widget.set_printing_active(True)
        
        # Start thread
        thread.start()
        
        logger.info(f"Started printing for server: {server.name}")
    
    def _stop_printing(self, server_id: str):
        """Stop printing for a specific server"""
        if server_id not in self.workers:
            return
        
        server = self.manager.get_server(server_id)
        
        # Confirm stop
        reply = QMessageBox.question(
            self,
            'Stop Print Process',
            f'Are you sure you want to stop printing on "{server.name}"?\n\nThis will send an ABORT command to the print server.',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        worker = self.workers[server_id]
        worker.cancel()
        
        logger.warning(f"Stopped printing for server: {server.name}")
    
    def _on_print_progress(self, server_id: str, processed: int, total: int, message: str):
        """Handle progress update"""
        if server_id in self.server_widgets:
            self.server_widgets[server_id].update_progress(processed, total, message)
    
    def _on_print_finished(self, server_id: str, success: bool):
        """Handle print completion"""
        if server_id in self.server_widgets:
            widget = self.server_widgets[server_id]
            widget.set_printing_active(False)
            
            if success:
                widget.update_progress(100, 100, "Printing completed successfully!")
                widget.append_server_info("✅ Print job completed")
            else:
                widget.update_progress(0, 100, "Printing failed or was cancelled")
                widget.append_server_info("⚠️ Print job failed or cancelled")
        
        # Cleanup
        if server_id in self.threads:
            # Just request quit without blocking - thread will clean up naturally
            self.threads[server_id].quit()
            del self.threads[server_id]
        
        if server_id in self.workers:
            del self.workers[server_id]
        
        server = self.manager.get_server(server_id)
        logger.info(f"Print job finished for server: {server.name} (success={success})")
    
    def _on_print_error(self, server_id: str, error_message: str):
        """Handle print error"""
        if server_id in self.server_widgets:
            widget = self.server_widgets[server_id]
            widget.update_progress(0, 100, f"Error: {error_message}")
            widget.append_server_info(f"❌ ERROR: {error_message}")
        
        server = self.manager.get_server(server_id)
        QMessageBox.critical(
            self,
            f"Print Error - {server.name}",
            f"An error occurred while printing:\n\n{error_message}"
        )
    
    def _on_connection_status(self, server_id: str, connected: bool, message: str):
        """Handle connection status update"""
        if server_id in self.server_widgets:
            widget = self.server_widgets[server_id]
            widget.set_connected(connected, message)
            widget.append_server_info(message)
    
    def _on_files_discovered(self, server_id: str, file_count: int):
        """Handle files discovered event"""
        if server_id in self.server_widgets:
            self.server_widgets[server_id].set_file_count(file_count)
    
    def _refresh_servers(self, show_message=True):
        """Refresh server list from configuration file"""
        # Clear current UI
        self.server_list.clear()
        self.server_widgets.clear()
        
        # Reload from manager (which reads from JSON file)
        self.manager = PrintServerManager()  # Create fresh instance to reload from file
        # Reconnect signals for new manager
        try:
            self.manager.server_added.connect(lambda _sid: self.rip2print_section.set_server_manager(self.manager))
            self.manager.server_updated.connect(lambda _sid: self.rip2print_section.set_server_manager(self.manager))
            self.manager.server_removed.connect(lambda _sid: self.rip2print_section.set_server_manager(self.manager))
        except Exception:
            pass
        # Update RIP2PRINT section with the new manager
        self.rip2print_section.set_server_manager(self.manager)
        
        # Reload servers
        self._load_servers()
        
        # Show success message only if requested
        if show_message:
            QMessageBox.information(
                self,
                "Servers Refreshed",
                "Server list has been refreshed from the configuration file."
            )
    
    def refresh_servers_external(self):
        """Public method to refresh servers (called from other sections)"""
        self._refresh_servers(show_message=False)  # Don't show message for external refreshes

