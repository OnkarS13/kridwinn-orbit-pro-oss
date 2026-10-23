"""
File Group Selector Widget - Enhanced with Per-Group Print Settings

Displays grouped RIP files and allows user to select, reorder, and configure
individual print settings for each group before printing.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QAbstractItemView, QCheckBox, QWidget,
    QSpinBox, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from typing import Dict, List
from pathlib import Path


class FileGroupSelector(QDialog):
    """
    Dialog for selecting, reordering, and configuring per-group print settings.

    Shows groups with individual settings for:
    - Page range (All/Range/Odd/Even)
    - Copies
    - Collation type
    - Reverse order
    """

    def __init__(self, groups: Dict[str, List[str]], global_settings: dict = None, enable_per_group_settings: bool = True, parent=None):
        """
        Initialize File Group Selector with per-group settings.

        Args:
            groups: Dict mapping group prefix to list of files
            global_settings: Global settings from main panel (used as defaults)
            enable_per_group_settings: If True, show full 10-column table with per-group settings.
                                       If False, show simplified 4-column table (selection/ordering only)
            parent: Parent widget
        """
        super().__init__(parent)
        self.groups = groups
        self.group_order = list(groups.keys())  # Initial order
        self.selected_groups = set(groups.keys())  # All selected by default
        self.enable_per_group_settings = enable_per_group_settings

        # Per-group settings storage (only if enabled)
        if self.enable_per_group_settings:
            self.group_settings = {}
            self._initialize_group_settings(global_settings or {})
        else:
            self.group_settings = None  # No per-group settings in simplified mode

        self.setWindowTitle("File Groups - Configure Print Settings")
        self.setMinimumSize(1200, 500)  # Wider for more columns

        # Apply explicit light theme stylesheet to ensure white mode regardless of parent theme
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
            QLabel {
                color: #212529;
            }
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8f9fa;
                color: #212529;
                gridline-color: #dee2e6;
            }
            QTableWidget::item {
                background-color: #ffffff;
                color: #212529;
            }
            QTableWidget::item:selected {
                background-color: #007bff;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                color: #212529;
                border: 1px solid #dee2e6;
                padding: 5px;
                font-weight: bold;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 5px;
                color: #212529;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #212529;
                selection-background-color: #007bff;
                selection-color: #ffffff;
            }
            QCheckBox {
                color: #212529;
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
            QPushButton:pressed {
                background-color: #004085;
            }
        """)

        self._setup_ui()
        self._populate_table()
        self._update_totals()

    def _initialize_group_settings(self, global_settings: dict):
        """Initialize per-group settings with smart defaults"""

        # Smart defaults (Option B from plan)
        default_range_mode = 'all'
        default_range_from = 1
        default_range_to = 1
        default_copies = 1
        default_collate = 1  # Collated
        default_reverse = False

        # Override with global settings if provided
        if global_settings:
            # Widget passes 'range_mode': 'all' or 'range', not 'range_mode_all'
            range_mode_value = global_settings.get('range_mode', 'all')
            if range_mode_value == 'all':
                default_range_mode = 'all'
            else:
                default_range_mode = 'range'
                # Get range_from and range_to when in range mode
                default_range_from = global_settings.get('range_from', 1)
                default_range_to = global_settings.get('range_to', 1)

            default_copies = global_settings.get('copies', 1)
            default_collate = global_settings.get('collate_type', 1)
            default_reverse = global_settings.get('reverse', False)

        for group_name in self.groups.keys():
            files = self.groups[group_name]
            total_pages = len(files)

            # Use global range values if provided, but cap at group's total_pages
            group_range_from = min(default_range_from, total_pages) if default_range_mode == 'range' else 1
            group_range_to = min(default_range_to, total_pages) if default_range_mode == 'range' else total_pages

            self.group_settings[group_name] = {
                'selected': True,
                'files': files,
                'total_pages': total_pages,
                'range_mode': default_range_mode,
                'range_from': group_range_from,
                'range_to': group_range_to,
                'copies': default_copies,
                'collate_type': default_collate,
                'reverse': default_reverse,
                'order': list(self.groups.keys()).index(group_name)
            }

    def _setup_ui(self):
        """Setup the UI layout"""
        layout = QVBoxLayout(self)

        # Header label
        if self.enable_per_group_settings:
            header_label = QLabel("Configure print settings for each group:")
        else:
            header_label = QLabel("Select and reorder file groups:")
        header_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(header_label)

        # Info banner when per-group settings disabled
        if not self.enable_per_group_settings:
            banner = QLabel("ℹ️ Per-group settings disabled. Global settings from main panel will be used.")
            banner.setStyleSheet("""
                background: #e3f2fd;
                color: #1565c0;
                padding: 8px;
                border-radius: 4px;
                font-size: 10pt;
            """)
            layout.addWidget(banner)

        # Instruction label (only for per-group mode)
        if self.enable_per_group_settings:
            inst_label = QLabel("Tip: Set settings for one group, then click 'Apply to All Groups' to copy those settings")
            inst_label.setStyleSheet("color: #666; font-size: 10pt;")
            layout.addWidget(inst_label)

        # Table widget
        self.table = QTableWidget()

        # Conditional column setup
        if self.enable_per_group_settings:
            # Full 10-column table with per-group settings
            self.table.setColumnCount(10)
            self.table.setHorizontalHeaderLabels([
                "", "Group Name", "Total", "Range", "From", "To",
                "Copies", "Collate", "Reverse", "Order"
            ])
        else:
            # Simplified 4-column table (selection + ordering only)
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels([
                "", "Group Name", "Total Pages", "Order"
            ])

        # Table settings
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        # Set text color to black for visibility
        self.table.setStyleSheet("""
            QTableWidget {
                color: black;
                background-color: white;
            }
            QTableWidget::item {
                color: black;
            }
            QHeaderView::section {
                color: black;
                background-color: #f0f0f0;
                padding: 4px;
                border: 1px solid #d0d0d0;
                font-weight: bold;
            }
        """)

        # Column widths
        header = self.table.horizontalHeader()
        if self.enable_per_group_settings:
            # Full 10-column layout
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Checkbox
            header.setSectionResizeMode(1, QHeaderView.Stretch)  # Group name
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Total
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Range
            header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # From
            header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # To
            header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Copies
            header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # Collate
            header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # Reverse
            header.setSectionResizeMode(9, QHeaderView.ResizeToContents)  # Up/Down
        else:
            # Simplified 4-column layout
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Checkbox
            header.setSectionResizeMode(1, QHeaderView.Stretch)  # Group name
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Total Pages
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Up/Down

        layout.addWidget(self.table)

        # Bottom controls
        bottom_layout = QHBoxLayout()

        # Apply to All and Reset buttons (only for per-group mode)
        if self.enable_per_group_settings:
            # Apply to All button (Quick Setup feature)
            apply_all_btn = QPushButton("Apply to All Groups")
            apply_all_btn.setToolTip("Copy settings from selected group to all other groups")
            apply_all_btn.clicked.connect(self._apply_to_all)
            bottom_layout.addWidget(apply_all_btn)

            # Reset to Defaults button
            reset_btn = QPushButton("Reset to Defaults")
            reset_btn.setToolTip("Reset all groups to default settings")
            reset_btn.clicked.connect(self._reset_to_defaults)
            bottom_layout.addWidget(reset_btn)

        bottom_layout.addStretch()

        # Total label
        self.total_label = QLabel()
        self.total_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        bottom_layout.addWidget(self.total_label)

        bottom_layout.addStretch()

        # Select All / Clear buttons
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        bottom_layout.addWidget(select_all_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self._clear_all)
        bottom_layout.addWidget(clear_btn)

        layout.addLayout(bottom_layout)

        # Dialog buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _populate_table(self):
        """Populate table with group data and settings controls"""
        self.table.setRowCount(len(self.group_order))

        for row, group_name in enumerate(self.group_order):
            # Column 0: Checkbox
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignCenter)

            checkbox = QCheckBox()
            checkbox.setChecked(group_name in self.selected_groups)
            checkbox.stateChanged.connect(lambda state, g=group_name: self._on_checkbox_changed(g, state))
            checkbox_layout.addWidget(checkbox)

            self.table.setCellWidget(row, 0, checkbox_widget)

            # Column 1: Group name
            name_item = QTableWidgetItem(group_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, name_item)

            # Column 2: Total pages (read-only)
            if self.enable_per_group_settings:
                settings = self.group_settings[group_name]
                total_item = QTableWidgetItem(str(settings['total_pages']))
            else:
                # In simplified mode, just count files
                total_item = QTableWidgetItem(str(len(self.groups[group_name])))
            total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
            total_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, total_item)

            if not self.enable_per_group_settings:
                # Simplified mode: Only render Up/Down buttons in column 3
                self._add_order_buttons(row, 3)
                continue

            # Per-group mode: Render all settings columns
            settings = self.group_settings[group_name]

            # Column 3: Range mode dropdown
            range_combo = QComboBox()
            range_combo.addItems(['All', 'Range', 'Odd', 'Even'])
            range_combo.setCurrentText(settings['range_mode'].capitalize())
            range_combo.currentTextChanged.connect(
                lambda text, r=row, g=group_name: self._on_range_mode_changed(g, text, r)
            )
            self.table.setCellWidget(row, 3, range_combo)

            # Column 4: From spinbox
            from_spin = QSpinBox()
            from_spin.setRange(1, settings['total_pages'])
            from_spin.setValue(settings['range_from'])
            from_spin.setEnabled(settings['range_mode'] == 'range')
            from_spin.valueChanged.connect(
                lambda val, g=group_name: self._on_range_from_changed(g, val)
            )
            self.table.setCellWidget(row, 4, from_spin)

            # Column 5: To spinbox
            to_spin = QSpinBox()
            to_spin.setRange(1, settings['total_pages'])
            to_spin.setValue(settings['range_to'])
            to_spin.setEnabled(settings['range_mode'] == 'range')
            to_spin.valueChanged.connect(
                lambda val, g=group_name: self._on_range_to_changed(g, val)
            )
            self.table.setCellWidget(row, 5, to_spin)

            # Column 6: Copies spinbox
            copies_spin = QSpinBox()
            copies_spin.setRange(1, 999)
            copies_spin.setValue(settings['copies'])
            copies_spin.valueChanged.connect(
                lambda val, g=group_name: self._on_copies_changed(g, val)
            )
            self.table.setCellWidget(row, 6, copies_spin)

            # Column 7: Collate dropdown
            collate_combo = QComboBox()
            collate_combo.addItems(['Collated', 'Uncollated'])
            collate_combo.setCurrentIndex(0 if settings['collate_type'] == 1 else 1)
            collate_combo.currentIndexChanged.connect(
                lambda idx, g=group_name: self._on_collate_changed(g, idx + 1)
            )
            self.table.setCellWidget(row, 7, collate_combo)

            # Column 8: Reverse checkbox
            reverse_widget = QWidget()
            reverse_layout = QHBoxLayout(reverse_widget)
            reverse_layout.setContentsMargins(0, 0, 0, 0)
            reverse_layout.setAlignment(Qt.AlignCenter)

            reverse_checkbox = QCheckBox()
            reverse_checkbox.setChecked(settings['reverse'])
            reverse_checkbox.stateChanged.connect(
                lambda state, g=group_name: self._on_reverse_changed(g, state == 2)
            )
            reverse_layout.addWidget(reverse_checkbox)

            self.table.setCellWidget(row, 8, reverse_widget)

            # Column 9: Up/Down buttons
            self._add_order_buttons(row, 9)

    def _add_order_buttons(self, row: int, column: int):
        """Add Up/Down ordering buttons to specified column"""
        btn_widget = QWidget()
        btn_layout = QHBoxLayout(btn_widget)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(2)

        up_btn = QPushButton("↑")
        up_btn.setToolTip("Move group up")
        up_btn.setMaximumWidth(35)
        up_btn.setMinimumHeight(30)
        up_btn.setStyleSheet("QPushButton { color: black; font-size: 14px; font-weight: bold; padding: 2px; }")
        up_btn.setEnabled(row > 0)
        up_btn.clicked.connect(lambda checked, r=row: self._move_up(r))
        btn_layout.addWidget(up_btn)

        down_btn = QPushButton("↓")
        down_btn.setToolTip("Move group down")
        down_btn.setMaximumWidth(35)
        down_btn.setMinimumHeight(30)
        down_btn.setStyleSheet("QPushButton { color: black; font-size: 14px; font-weight: bold; padding: 2px; }")
        down_btn.setEnabled(row < len(self.group_order) - 1)
        down_btn.clicked.connect(lambda checked, r=row: self._move_down(r))
        btn_layout.addWidget(down_btn)

        self.table.setCellWidget(row, column, btn_widget)

    # Event handlers for per-group settings
    def _on_range_mode_changed(self, group_name: str, mode_text: str, row: int):
        """Handle range mode change"""
        mode = mode_text.lower()
        self.group_settings[group_name]['range_mode'] = mode

        # Enable/disable From/To spinboxes
        from_spin = self.table.cellWidget(row, 4)
        to_spin = self.table.cellWidget(row, 5)

        if from_spin and to_spin:
            enabled = (mode == 'range')
            from_spin.setEnabled(enabled)
            to_spin.setEnabled(enabled)

        self._update_totals()

    def _on_range_from_changed(self, group_name: str, value: int):
        """Handle From value change with auto-adjustment"""
        settings = self.group_settings[group_name]

        # Auto-adjust if From > To
        if value > settings['range_to']:
            settings['range_to'] = value
            # Update To spinbox
            for row, g in enumerate(self.group_order):
                if g == group_name:
                    to_spin = self.table.cellWidget(row, 5)
                    if to_spin:
                        to_spin.setValue(value)
                    break

        # Auto-adjust if From > total_pages
        if value > settings['total_pages']:
            value = settings['total_pages']
            # Update From spinbox
            for row, g in enumerate(self.group_order):
                if g == group_name:
                    from_spin = self.table.cellWidget(row, 4)
                    if from_spin:
                        from_spin.setValue(value)
                    break

        settings['range_from'] = value
        self._update_totals()

    def _on_range_to_changed(self, group_name: str, value: int):
        """Handle To value change with auto-adjustment"""
        settings = self.group_settings[group_name]

        # Auto-adjust if To < From
        if value < settings['range_from']:
            settings['range_from'] = value
            # Update From spinbox
            for row, g in enumerate(self.group_order):
                if g == group_name:
                    from_spin = self.table.cellWidget(row, 4)
                    if from_spin:
                        from_spin.setValue(value)
                    break

        # Auto-adjust if To > total_pages
        if value > settings['total_pages']:
            value = settings['total_pages']
            # Update To spinbox
            for row, g in enumerate(self.group_order):
                if g == group_name:
                    to_spin = self.table.cellWidget(row, 5)
                    if to_spin:
                        to_spin.setValue(value)
                    break

        settings['range_to'] = value
        self._update_totals()

    def _on_copies_changed(self, group_name: str, value: int):
        """Handle copies change"""
        self.group_settings[group_name]['copies'] = value
        self._update_totals()

    def _on_collate_changed(self, group_name: str, collate_type: int):
        """Handle collation type change"""
        self.group_settings[group_name]['collate_type'] = collate_type
        self._update_totals()

    def _on_reverse_changed(self, group_name: str, reversed: bool):
        """Handle reverse order change"""
        self.group_settings[group_name]['reverse'] = reversed
        self._update_totals()

    def _on_checkbox_changed(self, group_name: str, state: int):
        """Handle checkbox state change"""
        is_checked = (state == 2)

        if is_checked:
            self.selected_groups.add(group_name)
        else:
            self.selected_groups.discard(group_name)

        # Update group settings if per-group mode is enabled
        if self.enable_per_group_settings:
            self.group_settings[group_name]['selected'] = is_checked

        self._update_totals()

    def _apply_to_all(self):
        """Apply settings from first selected group to all other groups"""
        # Get first selected/checked group
        source_group = None
        for group_name in self.group_order:
            if group_name in self.selected_groups:
                source_group = group_name
                break

        if not source_group:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "No Group Selected",
                "Please select at least one group to copy settings from."
            )
            return

        source_settings = self.group_settings[source_group]

        # Copy settings to all other groups (except range values which are group-specific)
        for group_name in self.groups.keys():
            if group_name != source_group:
                settings = self.group_settings[group_name]
                settings['range_mode'] = source_settings['range_mode']
                # Don't copy range_from/range_to - keep group-specific
                settings['copies'] = source_settings['copies']
                settings['collate_type'] = source_settings['collate_type']
                settings['reverse'] = source_settings['reverse']

        # Refresh table
        self._populate_table()
        self._update_totals()

        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Settings Applied",
            f"Settings from '{source_group}' applied to all other groups."
        )

    def _reset_to_defaults(self):
        """Reset all groups to default settings"""
        for group_name in self.groups.keys():
            settings = self.group_settings[group_name]
            settings['range_mode'] = 'all'
            settings['range_from'] = 1
            settings['range_to'] = settings['total_pages']
            settings['copies'] = 1
            settings['collate_type'] = 1
            settings['reverse'] = False

        # Refresh table
        self._populate_table()
        self._update_totals()

    def _move_up(self, row: int):
        """Move group up in order"""
        if row > 0:
            # Swap in order list
            self.group_order[row], self.group_order[row - 1] = \
                self.group_order[row - 1], self.group_order[row]

            # Refresh table
            self._populate_table()

    def _move_down(self, row: int):
        """Move group down in order"""
        if row < len(self.group_order) - 1:
            # Swap in order list
            self.group_order[row], self.group_order[row + 1] = \
                self.group_order[row + 1], self.group_order[row]

            # Refresh table
            self._populate_table()

    def _select_all(self):
        """Select all groups"""
        self.selected_groups = set(self.group_order)
        if self.enable_per_group_settings:
            for group_name in self.groups.keys():
                self.group_settings[group_name]['selected'] = True
        self._populate_table()
        self._update_totals()

    def _clear_all(self):
        """Deselect all groups"""
        self.selected_groups.clear()
        if self.enable_per_group_settings:
            for group_name in self.groups.keys():
                self.group_settings[group_name]['selected'] = False
        self._populate_table()
        self._update_totals()

    def _calculate_filtered_pages(self, group_name: str) -> int:
        """Calculate actual pages after filtering (for accurate totals)"""
        settings = self.group_settings[group_name]
        total_pages = settings['total_pages']

        if settings['range_mode'] == 'all':
            return total_pages
        elif settings['range_mode'] == 'range':
            range_size = settings['range_to'] - settings['range_from'] + 1
            # Defensive: ensure range_size is non-negative (auto-adjust should prevent this)
            return min(max(0, range_size), total_pages)
        elif settings['range_mode'] == 'odd':
            return (total_pages + 1) // 2
        elif settings['range_mode'] == 'even':
            return total_pages // 2

        return total_pages

    def _update_totals(self):
        """Update total pages label (accounting for filtering and copies)"""
        total_groups = len(self.selected_groups)
        total_pages = 0

        if self.enable_per_group_settings:
            # Per-group mode: Calculate with filters and copies
            for group_name in self.selected_groups:
                filtered_pages = self._calculate_filtered_pages(group_name)
                copies = self.group_settings[group_name]['copies']
                total_pages += filtered_pages * copies
            self.total_label.setText(
                f"Selected: {total_groups} group(s), {total_pages} total prints"
            )
        else:
            # Simplified mode: Simple page count without filters/copies
            for group_name in self.selected_groups:
                total_pages += len(self.groups[group_name])
            self.total_label.setText(
                f"Selected: {total_groups} group(s), {total_pages} pages"
            )

    # Public methods for retrieving settings
    def get_group_settings(self) -> Dict:
        """Get per-group settings for selected groups only"""
        # Return empty dict if per-group settings are disabled
        if not self.enable_per_group_settings or self.group_settings is None:
            return {}

        selected_settings = {}
        for group_name in self.selected_groups:
            selected_settings[group_name] = self.group_settings[group_name].copy()
        return selected_settings

    def get_print_order(self) -> List[str]:
        """Get ordered list of selected group names"""
        return [g for g in self.group_order if g in self.selected_groups]

    def get_selected_files(self) -> List[str]:
        """
        Get files from selected groups in current order.
        (For backward compatibility)

        Returns:
            Flat list of files from selected groups
        """
        result = []
        for group_name in self.group_order:
            if group_name in self.selected_groups:
                result.extend(self.groups[group_name])
        return result

    def get_total_pages(self) -> int:
        """
        Get total number of selected pages (accounting for filters and copies).

        Returns:
            Total page count
        """
        total = 0
        for group_name in self.selected_groups:
            filtered_pages = self._calculate_filtered_pages(group_name)
            copies = self.group_settings[group_name]['copies']
            total += filtered_pages * copies
        return total

    def get_selected_groups(self) -> List[str]:
        """
        Get selected group names in current order.
        (For backward compatibility)

        Returns:
            Ordered list of selected group names
        """
        return [g for g in self.group_order if g in self.selected_groups]

    def accept(self):
        """Override accept to validate selection"""
        if not self.selected_groups:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "No Groups Selected",
                "Please select at least one group to print."
            )
            return

        super().accept()
