from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton


class JobTypeSelector(QWidget):
    """Select between Single Server and Dual Server job submissions."""

    job_type_selected = Signal(str)  # "single" | "dual"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.single_btn = QPushButton("JOB SUBMISSION (Single Server)")
        self.dual_btn = QPushButton("JOB SUBMISSION (Dual Server)")
        layout.addWidget(self.single_btn)
        layout.addWidget(self.dual_btn)
        self.single_btn.clicked.connect(lambda: self.job_type_selected.emit("single"))
        self.dual_btn.clicked.connect(lambda: self.job_type_selected.emit("dual"))


