from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy


class ModeSelectorWidget(QWidget):
    """
    Top-level mode selector: RIP2PRINT | IMG2PRINT | PDF2PRINT.
    Lightweight placeholder; styling and callbacks can be enhanced later.
    """

    mode_selected = Signal(str)  # "rip2print", "img2print", "pdf2print"

    def __init__(self, parent=None):
        super().__init__(parent)
        # Use vertical layout with stretch-based spacing like PDF Desk
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(2)
        row = QHBoxLayout()
        row.setSpacing(0)
        row.addStretch()
        self.rip_btn = QPushButton("RIP2PRINT"); self.rip_btn.setCheckable(True)
        self.img_btn = QPushButton("IMG2PRINT"); self.img_btn.setCheckable(True)
        self.pdf_btn = QPushButton("PDF2PRINT"); self.pdf_btn.setCheckable(True)
        self.legacy_btn = QPushButton("🛠️ SERVER CTRL"); self.legacy_btn.setCheckable(True)
        # Make buttons large, centered, evenly spaced
        buttons_to_show = [self.rip_btn, self.img_btn, self.pdf_btn]
        for idx, btn in enumerate(buttons_to_show):
            btn.setMinimumSize(200, 80)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            row.addWidget(btn)
            # 40px gap between visible buttons
            if idx < len(buttons_to_show) - 1:
                row.addSpacing(40)
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch(3)
        # basic styling
        # PDF Desk button styles per button
        self.rip_btn.setStyleSheet(
            """
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #0056b3; }
            """
        )
        self.img_btn.setStyleSheet(
            """
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #0056b3; }
            """
        )
        self.pdf_btn.setStyleSheet(
            """
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #0056b3; }
            """
        )
        self.legacy_btn.setStyleSheet(
            """
            QPushButton { font-size: 18pt; font-weight: bold; background-color: #6c757d; color: white; border-radius: 10px; padding: 20px; }
            QPushButton:hover { background-color: #5a6268; }
            """
        )
        self.rip_btn.clicked.connect(lambda: self._on_click("rip2print"))
        self.img_btn.clicked.connect(lambda: self._on_click("img2print"))
        self.pdf_btn.clicked.connect(lambda: self._on_click("pdf2print"))
        self.legacy_btn.clicked.connect(lambda: self._on_click("legacy"))

        # Hide SERVER CTRL button for now as requested
        self.legacy_btn.setVisible(False)

    def _on_click(self, mode: str):
        self.set_active(mode)
        self.mode_selected.emit(mode)

    def set_active(self, mode: str):
        self.rip_btn.setChecked(mode == "rip2print")
        self.img_btn.setChecked(mode == "img2print")
        self.pdf_btn.setChecked(mode == "pdf2print")
        self.legacy_btn.setChecked(mode == "legacy")


