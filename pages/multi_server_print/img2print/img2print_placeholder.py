from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class IMG2PrintPlaceholder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("Under Development")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 24pt; font-weight: bold; color: #6c757d;")
        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()


