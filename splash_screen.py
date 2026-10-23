"""
Splash Screen Module for Kridwinn Orbit Pro
Displays a fullscreen splash screen with company logo and fades out after 2-3 seconds
"""

import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QSplashScreen, QApplication
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor


class SplashScreen(QSplashScreen):
    """
    Custom splash screen with company logo and text.
    Displays fullscreen for 2-3 seconds with a fade-out effect.
    """
    
    def __init__(self):
        super().__init__()
        
        # Load company logo
        logo_path = Path(__file__).parent / "assets" / "company_logo.png"
        
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            # Scale the pixmap to a reasonable size for splash screen
            # You can adjust these dimensions as needed
            scaled_pixmap = pixmap.scaled(800, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            # Fallback: create a blank pixmap if logo not found
            scaled_pixmap = QPixmap(800, 600)
            scaled_pixmap.fill(QColor(255, 255, 255))
        
        # Create a larger canvas for fullscreen display
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        
        # Create canvas with screen dimensions
        canvas = QPixmap(screen_size)
        canvas.fill(QColor(255, 255, 255))  # White background
        
        # Draw logo and text on canvas
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # Calculate centered position for logo
        logo_x = (screen_size.width() - scaled_pixmap.width()) // 2
        logo_y = (screen_size.height() - scaled_pixmap.height()) // 2 - 50  # Offset up for text below
        
        # Draw logo
        painter.drawPixmap(logo_x, logo_y, scaled_pixmap)
        
        # Draw text below logo
        painter.setPen(QColor(0, 0, 0))  # Black text

        # App name
        app_name = "Kridwinn Orbit Pro"
        name_font = QFont("Segoe UI", 34, QFont.Bold)
        painter.setFont(name_font)
        name_rect = painter.fontMetrics().boundingRect(app_name)
        name_x = (screen_size.width() - name_rect.width()) // 2
        name_y = logo_y + scaled_pixmap.height() + 80
        painter.drawText(name_x, name_y, app_name)

        # Version text
        version_text = "Version 25.11.001Beta"
        version_font = QFont("Segoe UI", 20, QFont.Normal)
        painter.setFont(version_font)
        version_rect = painter.fontMetrics().boundingRect(version_text)
        version_x = (screen_size.width() - version_rect.width()) // 2
        version_y = name_y + version_rect.height() + 10
        painter.drawText(version_x, version_y, version_text)

        # Footer text
        footer_text = "© Kridwinn Innovations Private Limited. All rights reserved."
        footer_font = QFont("Segoe UI", 14, QFont.Normal)
        painter.setFont(footer_font)
        footer_rect = painter.fontMetrics().boundingRect(footer_text)
        footer_x = (screen_size.width() - footer_rect.width()) // 2
        footer_y = screen_size.height() - footer_rect.height() - 40
        painter.drawText(footer_x, footer_y, footer_text)
        painter.end()
        
        # Set the canvas as splash screen pixmap
        self.setPixmap(canvas)
        
        # Set window flags for fullscreen and always on top
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.SplashScreen)
        
        # Set window attributes to ensure immediate display
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        
        # Show fullscreen immediately
        self.showFullScreen()
        
        # Force immediate rendering
        self.raise_()
        self.activateWindow()
        
        # Set up fade-out animation
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(500)  # 500ms fade duration
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Connect animation finished to close
        self.fade_animation.finished.connect(self.close)
        
        # Timer to start fade-out after 2.5 seconds
        QTimer.singleShot(2500, self.start_fade_out)
    
    def start_fade_out(self):
        """Start the fade-out animation"""
        self.fade_animation.start()


def show_splash_screen(app):
    """
    Show the splash screen and return it.
    
    Args:
        app: QApplication instance
        
    Returns:
        SplashScreen instance
    """
    splash = SplashScreen()
    return splash


if __name__ == "__main__":
    # Test the splash screen independently
    app = QApplication(sys.argv)
    splash = show_splash_screen(app)
    sys.exit(app.exec())

