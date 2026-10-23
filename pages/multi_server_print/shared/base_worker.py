from PySide6.QtCore import QObject, Signal


class BaseWorker(QObject):
    """
    Base worker providing common signals for background tasks.
    """

    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(bool)           # success flag
    error = Signal(str)               # error message

    def cancel(self):
        """Override in subclasses to support cooperative cancellation."""
        pass


