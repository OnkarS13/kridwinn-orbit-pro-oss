"""
Worker class for checking dimensions of a single PDF file in background thread.
This can be imported and used in the split section.
"""

from PySide6.QtCore import QObject, Signal
import time
from .pdf_dimension_checker import check_pdf_dimensions_threaded, get_dimension_summary, format_dimensions


class SinglePDFDimensionCheckWorker(QObject):
    """Worker for checking dimensions of a single PDF file"""
    finished = Signal()
    error = Signal(str)
    progress = Signal(int, str)  # percentage, message
    result = Signal(dict)  # dimension check result

    def __init__(self, pdf_path: str):
        super().__init__()
        self.pdf_path = pdf_path
        self._last_emit_time = 0.0
        self._last_emit_percent = -1

    def _throttled_progress(self, percent: int, message: str):
        """Emit progress updates at most every 60 ms and only when percent changes."""
        now = time.time()
        if percent == self._last_emit_percent and (now - self._last_emit_time) < 0.06:
            return
        self._last_emit_percent = percent
        self._last_emit_time = now
        try:
            self.progress.emit(percent, message)
        except Exception:
            pass

    def run(self):
        try:
            # Use the threaded checker with progress callback
            result = check_pdf_dimensions_threaded(self.pdf_path, self._throttled_progress)
            
            # Add formatted summary
            result['summary'] = get_dimension_summary(result)
            if result['unique_dimensions']:
                result['formatted_dimensions'] = [
                    format_dimensions(dim) for dim in result['unique_dimensions']
                ]
            
            self.result.emit(result)
            
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()
