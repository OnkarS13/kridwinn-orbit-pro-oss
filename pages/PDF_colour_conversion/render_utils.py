from typing import Tuple
from PySide6.QtGui import QImage

def qimage_from_page(page, x_dpi: int, y_dpi: int) -> QImage:
    """
    Render a PyMuPDF page to QImage using separate X and Y DPI.
    Returns a detached QImage safe for use in Qt.
    """
    import fitz
    from PySide6.QtGui import QImage

    scale_x = max(1.0, float(x_dpi) / 72.0)
    scale_y = max(1.0, float(y_dpi) / 72.0)
    mat = fitz.Matrix(scale_x, scale_y)
    pix = page.get_pixmap(matrix=mat)
    
    # Create QImage with explicit byte copy
    if pix.alpha:
        fmt = QImage.Format_RGBA8888
    else:
        fmt = QImage.Format_RGB888
    
    # Copy bytes BEFORE pix is destroyed
    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
    
    # Explicitly delete pixmap to free memory
    pix = None
    
    return qimg


def clamp_dpi(value: int) -> int:
    return max(72, min(2400, int(value)))


