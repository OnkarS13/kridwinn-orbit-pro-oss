from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame


class LiveStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_error = False
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(18, 18, 18, 18)
        self._main_layout.setSpacing(16)
        
        # Title
        self.title = QLabel("<b>Live Status</b>")
        self.title.setStyleSheet("font-size: 14px; color: #212529; letter-spacing: 0.3px;")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._main_layout.addWidget(self.title)

        # Bento-style cards
        self._cards_layout = QHBoxLayout()
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(12)

        self._accent_colors = {
            "sent": "#0d6efd",
            "printed": "#2f9e44",
            "speed": "#0ca678",
            "muted": "#adb5bd",
        }

        self.sent_card, self.sent_value = self._create_card("Files Sent", self._accent_colors["sent"], "0 / 0 (0%)")
        self.printed_card, self.printed_value = self._create_card("Files Printed", self._accent_colors["printed"], "0 / 0 (0%)")
        self.speed_card, self.speed_value = self._create_card("Speed", self._accent_colors["speed"], "--")

        self._cards = [self.sent_card, self.printed_card, self.speed_card]

        self._cards_layout.addWidget(self.sent_card)
        self._cards_layout.addWidget(self.printed_card)
        self._cards_layout.addWidget(self.speed_card)
        self._cards_layout.setStretch(0, 1)
        self._cards_layout.setStretch(1, 1)
        self._cards_layout.setStretch(2, 1)

        self._main_layout.addLayout(self._cards_layout)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        self._main_layout.addWidget(line)
        
        # Error message label (hidden by default)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("font-weight: 500; color: #e03131; font-size: 12px; padding: 4px 0;")
        self.error_label.setVisible(False)
        self._main_layout.addWidget(self.error_label)

        self._apply_normal_style()

    def _apply_normal_style(self):
        """Apply normal (non-error) styling"""
        self.setStyleSheet(
            """
            QWidget { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 18px; }
            """
        )
        self.title.setStyleSheet("font-size: 14px; color: #212529; letter-spacing: 0.3px;")
        self._apply_card_style(normal=True)
        self._reset_value_styles()
    
    def _apply_error_style(self):
        """Apply error styling with red background"""
        self.setStyleSheet(
            """
            QWidget { background-color: #fff5f5; border: 1px solid #fa5252; border-radius: 18px; }
            """
        )
        self.title.setText("<b>Live Status</b>")
        self.title.setStyleSheet("font-size: 14px; color: #c92a2a; letter-spacing: 0.3px; font-weight: bold;")
        self._apply_card_style(normal=False)

    def update_status(self, sent: int, printed: int, total: int, speed: Optional[float] = None) -> None:
        """Update status display with optional speed feedback."""
        if self._is_error:
            return  # Don't update if in error state
        
        sent_pct = int((sent / total) * 100) if total > 0 else 0
        printed_pct = int((printed / total) * 100) if total > 0 else 0
        self.sent_value.setText(f"{sent} / {total} ({sent_pct}%)")
        self._set_value_style(self.sent_value, self._accent_colors["sent"])

        self.printed_value.setText(f"{printed} / {total} ({printed_pct}%)")
        printed_color = "#dc3545" if printed_pct < 25 else ("#f08c00" if printed_pct < 75 else self._accent_colors["printed"])
        self._set_value_style(self.printed_value, printed_color)

        if speed is None:
            self.speed_value.setText("--")
            self._set_value_style(self.speed_value, self._accent_colors["muted"])
        else:
            try:
                speed_val = float(speed)
                self.speed_value.setText(f"{speed_val:.1f} m/min")
                self._set_value_style(self.speed_value, self._accent_colors["speed"])
            except (TypeError, ValueError):
                self.speed_value.setText("--")
                self._set_value_style(self.speed_value, self._accent_colors["muted"])
    
    def show_error(self, error_message: str, last_sent: int = 0, last_printed: int = 0, total: int = 0):
        """Show error state with last known counts"""
        self._is_error = True
        self._apply_error_style()
        
        # Gray out the counts to show they're the last known values
        if total > 0:
            sent_pct = int((last_sent / total) * 100)
            printed_pct = int((last_printed / total) * 100)
            self.sent_value.setText(f"{last_sent} / {total} ({sent_pct}%) • Last known")
            self.printed_value.setText(f"{last_printed} / {total} ({printed_pct}%) • Last known")
        else:
            self.sent_value.setText("-- / --")
            self.printed_value.setText("-- / --")
        
        self._set_value_style(self.sent_value, self._accent_colors["muted"])
        self._set_value_style(self.printed_value, self._accent_colors["muted"])
        self.speed_value.setText("--")
        self._set_value_style(self.speed_value, self._accent_colors["muted"])
        
        # Show error message
        self.error_label.setText(error_message)
        self.error_label.setVisible(True)
    
    def clear_error(self):
        """Clear error state and return to normal"""
        self._is_error = False
        self._apply_normal_style()
        self.title.setText("<b>Live Status</b>")
        self.error_label.setVisible(False)
        self._reset_value_styles()

    def _create_card(self, title: str, accent_color: str, initial_value: str):
        card = QFrame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #495057; font-size: 11px; letter-spacing: 0.3px; text-transform: uppercase;")
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        value_label = QLabel(initial_value)
        self._set_value_style(value_label, accent_color)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addStretch()

        return card, value_label

    def _set_value_style(self, label: QLabel, color: str):
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        label.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 600;")

    def _apply_card_style(self, normal: bool = True):
        if normal:
            bg = "#ffffff"
            border = "#e9ecef"
        else:
            bg = "#fff2f3"
            border = "#ffc9c9"

        style = f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 16px;
            }}
        """
        for card in self._cards:
            card.setStyleSheet(style)

    def _reset_value_styles(self):
        self._set_value_style(self.sent_value, self._accent_colors["sent"])
        self._set_value_style(self.printed_value, self._accent_colors["printed"])
        self._set_value_style(self.speed_value, self._accent_colors["speed"])


