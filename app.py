import sys
import os
import warnings

# Suppress Google API warnings about Python 3.9.12 compatibility
warnings.filterwarnings('ignore', category=FutureWarning, module='google.api_core')
warnings.filterwarnings('ignore', message='.*importlib.metadata.*packages_distributions.*')
warnings.filterwarnings('ignore', message='.*You are using a Python version.*past its end of life.*')

# Suppress importlib.metadata errors in stderr
_original_stderr = sys.stderr
class FilteredStderr:
    def __init__(self, original):
        self.original = original
    def write(self, message):
        if 'importlib.metadata' in message and 'packages_distributions' in message:
            return
        if 'FutureWarning' in message and 'google.api_core' in message:
            return
        if 'You are using a Python version' in message and 'past its end of life' in message:
            return
        self.original.write(message)
    def flush(self):
        self.original.flush()
    def __getattr__(self, name):
        return getattr(self.original, name)

# Only filter if not already filtered
if not isinstance(sys.stderr, FilteredStderr):
    sys.stderr = FilteredStderr(sys.stderr)

import time
import socket
import logging
from pathlib import Path
from datetime import datetime
import uuid
import fitz  # PyMuPDF for rendering previews
from PySide6.QtCore import Qt, QThread, Signal, QObject, QSize
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QComboBox, QTextEdit,
    QSplitter, QGroupBox, QMessageBox, QScrollArea, QStackedWidget,
    QFileDialog, QSpinBox, QRadioButton, QButtonGroup, QProgressBar, QListView, QCheckBox,
    QDialog
)
from PySide6.QtGui import QPalette, QColor, QFont, QPixmap, QImage, QIcon, QFontDatabase
from pages.pdf_to_image_converter.pdf_to_image_converter import PDFToImageConverter
from pages.pdf_to_image_converter.pdf_render_section import PDFRenderSection
from pages.PDF_colour_conversion.pdf_colour_conversion_section import PDFColourConversionSection
from pages.merge_split.pdf_split_section import PDFSplitSection
from pages.page_impose.page_impose_section import PageImposeSection
from pages.images_to_rip.images_to_rip import ClientPool, ParallelImageRipProcessor
from pages.rip_to_print.rip_to_print import GUIRipPrinter
from pages.multi_server_print.multi_server_section import MultiServerPrintSection
from pages.print_server_config.print_server_config_section import PrintServerConfigSection
from pages.login import LoginDialog
from splash_screen import show_splash_screen

# Set up logging for abort functionality
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# --- Session Logger ---------------------------------------------------------
class SessionLogger:
    """Creates logs/<YYYY-MM-DD>/<session_id>/ and wires file handlers.

    Files created per session:
      - app.log              (root app/debug/errors)
      - pdf_conversion.log   (PDF section params + results)
      - images_to_rip.log    (images_to_rip module logs)
      - print_rip.log        (rip_to_print module logs)
      - connection.log       (connection/status lines from Print section)
    """

    def __init__(self, base_dir: Path = Path("logs")):
        self.base_dir = base_dir
        self.date_dir = self.base_dir / datetime.now().strftime("%Y-%m-%d")
        session_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uid = str(uuid.uuid4()).split('-')[0]
        self.session_id = f"{session_stamp}_{short_uid}"
        self.session_dir = self.date_dir / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Keep handlers to close later
        self._handlers = []

        # Root/app logger
        self._add_file_handler(logging.getLogger(), self.session_dir / "app.log", level=logging.INFO)

        # Section/module loggers
        self.pdf_logger = logging.getLogger("pdf")
        self._add_file_handler(self.pdf_logger, self.session_dir / "pdf_conversion.log", level=logging.INFO)

        self.images_logger = logging.getLogger("images_to_rip")
        self._add_file_handler(self.images_logger, self.session_dir / "images_to_rip.log", level=logging.INFO)

        self.print_logger = logging.getLogger("rip_to_print")
        self._add_file_handler(self.print_logger, self.session_dir / "print_rip.log", level=logging.INFO)

        self.conn_logger = logging.getLogger("connection")
        self._add_file_handler(self.conn_logger, self.session_dir / "connection.log", level=logging.INFO)

        # Make module loggers not double-propagate to root if noisy
        for lg in (self.images_logger, self.print_logger, self.pdf_logger, self.conn_logger):
            lg.propagate = True  # keep also in app.log; set False to isolate

        logging.getLogger(__name__).info(f"Session started: {self.session_dir}")

    def _add_file_handler(self, logger_obj: logging.Logger, file_path: Path, level=logging.INFO):
        handler = logging.FileHandler(str(file_path), encoding='utf-8')
        handler.setLevel(level)
        fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        handler.setFormatter(fmt)
        logger_obj.addHandler(handler)
        self._handlers.append((logger_obj, handler))

    def close(self):
        logging.getLogger(__name__).info("Closing session log handlers")
        for logger_obj, handler in self._handlers:
            try:
                logger_obj.removeHandler(handler)
                handler.close()
            except Exception:
                pass

    def get_session_dir(self) -> Path:
        return self.session_dir



# --- GIS Abort Client (Based on abort.py) ---
class GISAbortClient:
    """Minimal client for aborting GIS Print Server operations"""
    
    def __init__(self, host='localhost', port=2000):
        """
        Initialize abort client
        
        Args:
            host: IP address or hostname of the Print Server
            port: Port number (default 2000)
        """
        self.host = host
        self.port = port
        self.socket = None
        
    def connect(self):
        """Establish connection to the Print Server"""
        try:
            logger.info(f"Connecting to Print Server for abort at {self.host}:{self.port}...")
            
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Set socket options for better performance
            try:
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except:
                pass
                
            # Connect with timeout
            self.socket.settimeout(10)  # 10 second timeout
            self.socket.connect((self.host, self.port))
            
            # Handle connection handshake
            response = self._receive_message()
            logger.info(f"Abort connection response: {response}")
            
            # Handle authentication if required
            if response.startswith("N,A"):
                # Authentication required
                auth_key = response.split(',')[2].strip()
                logger.info("Authentication required for abort, sending response...")
                
                # Simple echo authentication (modify if needed)
                self._send_message(f"N,R,{auth_key}")
                response = self._receive_message()
                
            if "N,C" in response:
                logger.info("Successfully connected to Print Server for abort")
                return True
            else:
                logger.error(f"Failed to connect for abort: {response}")
                return False
                
        except socket.timeout:
            logger.error("Abort connection timeout - Print Server not responding")
            return False
        except Exception as e:
            logger.error(f"Abort connection error: {e}")
            return False
            
    def _send_message(self, message):
        """Send a message to the Print Server"""
        if not self.socket:
            raise Exception("Not connected to server for abort")
            
        message_with_newline = message + '\n'
        self.socket.send(message_with_newline.encode())
        logger.debug(f"Sent abort: {message}")
        
    def _receive_message(self):
        """Receive a single message from the Print Server"""
        if not self.socket:
            raise Exception("Not connected to server for abort")
            
        response = b""
        while b'\n' not in response:
            chunk = self.socket.recv(1024)
            if not chunk:
                break
            response += chunk
                
        return response.decode().strip()
        
    def send_abort(self):
        """Send abort command to the Print Server"""
        try:
            logger.warning("Sending ABORT command...")
            
            # Send abort command
            self._send_message("P,A")
            
            # Wait for acknowledgement
            response = self._receive_message()
            if response.startswith("A,"):
                logger.info("Abort command acknowledged")
                
                # Wait for completion (optional)
                self.socket.settimeout(5)
                try:
                    complete = self._receive_message()
                    if complete.startswith("C,"):
                        parts = complete.split(',')
                        if len(parts) >= 3:
                            error_code = int(parts[2])
                            if error_code == 0:
                                logger.info("Abort completed successfully")
                            else:
                                logger.warning(f"Abort completed with code: {error_code}")
                except socket.timeout:
                    logger.info("No completion message received (normal for abort)")
                    
                return True
            else:
                logger.error(f"Unexpected response to abort: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send abort: {e}")
            return False
            
    def close(self):
        """Close the connection"""
        if self.socket:
            try:
                self.socket.close()
                logger.info("Abort connection closed")
            except:
                pass
            self.socket = None


def abort_print_server_operations(host='localhost', port=2000):
    """
    Abort operations on GIS Print Server
    
    Args:
        host: Server hostname/IP
        port: Server port
    
    Returns:
        bool: True if successful
    """
    success = False
    
    # Create abort client
    client = GISAbortClient(host, port)
    
    try:
        # Connect to server
        if not client.connect():
            logger.error("Failed to connect to Print Server for abort")
            return False
            
        # Send abort command
        logger.info("Aborting Print Controller operations...")
        success = client.send_abort()
                
    except Exception as e:
        logger.error(f"Abort operation failed: {e}")
        success = False
        
    finally:
        client.close()
        
    return success


# --- Style Sheet (Google-inspired) ---
STYLESHEET = """
    QMainWindow, QWidget {
        background-color: #f8f9fa; /* Light gray background */
        /* Prefer Google Sans/Product Sans if available, fall back to system */
        font-family: 'Google Sans', 'Product Sans', Arial, sans-serif;
        font-size: 10pt;
    }
    QGroupBox {
        background-color: #ffffff; /* White background for cards */
        border: 1px solid #dee2e6; /* Light border */
        border-radius: 8px;
        margin-top: 1ex; /* Spacing for title */
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        background-color: #ffffff;
        color: #495057; /* Darker gray for titles */
    }
    QLabel {
        color: #212529; /* Dark text color */
        padding: 2px;
    }
    QCheckBox {
        color: #212529; /* Dark text color for checkboxes */
    }
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
    }
    QCheckBox::indicator:unchecked {
        border: 2px solid #ced4da;
        border-radius: 3px;
        background-color: #ffffff;
    }
    QCheckBox::indicator:checked {
        border: 2px solid #007bff;
        border-radius: 3px;
        background-color: #007bff;
    }
    QRadioButton {
        color: #212529; /* Dark text color for radio buttons */
    }
    QRadioButton::indicator {
        width: 18px;
        height: 18px;
    }
    QRadioButton::indicator::unchecked {
        border: 2px solid #ced4da;
        border-radius: 9px;
        background-color: #ffffff;
    }
    QRadioButton::indicator::checked {
        border: 2px solid #007bff;
        border-radius: 9px;
        background-color: #007bff;
    }
    QLineEdit, QComboBox, QTextEdit, QListWidget, QSpinBox {
        background-color: #ffffff;
        border: 1px solid #ced4da;
        border-radius: 4px;
        padding: 5px;
        color: #212529;
    }
    QComboBox QAbstractItemView {
        background-color: #ffffff; 
        color: #212529;          /* Dark text for dropdown items */
        selection-background-color: #007bff; 
        selection-color: #ffffff;          
        border: 1px solid #ced4da;       
        padding: 2px; 
    }
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QListWidget:focus {
        border-color: #80bdff; /* Blue border on focus */
        outline: 0;
    }
    QPushButton {
        background-color: #007bff; /* Primary blue */
        color: white;
        border: none;
        padding: 8px 15px;
        border-radius: 4px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #0056b3; /* Darker blue on hover */
    }
    QPushButton:pressed {
        background-color: #004085; /* Even darker blue when pressed */
    }
    QPushButton#SectionButton {
        background-color: #f8f9fa; /* Off-white when inactive */
        color: #212529;            /* Dark text when inactive */
        border: 1px solid #ced4da; /* Subtle border */
        font-size: 12pt;
        padding: 12px 20px;
        margin: 5px;
    }
    QPushButton#SectionButton:hover {
        background-color: #e9ecef; /* Slightly darker off-white on hover */
    }
    QPushButton#SectionButton:pressed {
        background-color: #dee2e6; /* Pressed state for inactive */
    }
    QPushButton#SectionButton[active="true"] {
        background-color: #28a745; /* Green when active */
        color: #ffffff;            /* White text when active */
        border: none;
    }
    QPushButton#SectionButton[active="true"]:hover {
        background-color: #218838; /* Darker green on hover when active */
    }
    QPushButton#SecondaryButton {
        background-color: #6c757d; /* Secondary gray */
    }
    QPushButton#SecondaryButton:hover {
        background-color: #5a6268;
    }
    QPushButton#SecondaryButton:pressed {
        background-color: #545b62;
    }
    QPushButton#StopButton {
        background-color: #dc3545; /* Red for stop button */
    }
    QPushButton#StopButton:hover {
        background-color: #c82333;
    }
    QPushButton#StopButton:pressed {
        background-color: #bd2130;
    }
    QSplitter::handle {
        background-color: #dee2e6; /* Light gray for splitter handle */
    }
    QScrollBar:vertical {
        border: 1px solid #ced4da;
        background: #f8f9fa;
        width: 12px;
        margin: 0px 0px 0px 0px;
    }
    QScrollBar::handle:vertical {
        background: #adb5bd;
        min-height: 20px;
        border-radius: 6px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
        background: none;
    }
    QScrollBar:horizontal {
        border: 1px solid #ced4da;
        background: #f8f9fa;
        height: 12px;
        margin: 0px 0px 0px 0px;
    }
    QScrollBar::handle:horizontal {
        background: #adb5bd;
        min-width: 20px;
        border-radius: 6px;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
        background: none;
    }
    QProgressBar {
        border: 1px solid #ced4da;
        border-radius: 4px;
        text-align: center;
        background-color: #f8f9fa;
    }
    QProgressBar::chunk {
        background-color: #007bff;
        border-radius: 3px;
    }
"""

def _apply_global_font():
    """
    Try to set the application font to Google Sans/Product Sans if available.
    Looks for TTFs under a local 'fonts' directory. Falls back to system default.
    """
    try:
        # Attempt to load bundled fonts if present
        fonts_dir = Path('fonts')
        loaded_families = []
        if fonts_dir.exists():
            for ttf in fonts_dir.glob('*.ttf'):
                fid = QFontDatabase.addApplicationFont(str(ttf))
                if fid != -1:
                    loaded_families.extend(QFontDatabase.applicationFontFamilies(fid))
        # Choose preferred family
        preferred = None
        for name in ("Google Sans", "Product Sans"):
            if name in QFontDatabase.families() or name in loaded_families:
                preferred = name
                break
        if preferred:
            QApplication.setFont(QFont(preferred))
        else:
            # Fall back gently to a clean sans font
            QApplication.setFont(QFont("Arial"))
    except Exception:
        pass

# --- PDF Conversion Worker Thread ---
class PDFConversionWorker(QObject):
    """
    Worker object to handle PDF conversion in a separate thread.
    """
    finished = Signal()
    progress = Signal(int, str)  # progress percentage, status message
    error = Signal(str)  # error message

    def __init__(self, pdf_path, output_dir, dpi, rotation_deg):
        super().__init__()
        self.pdf_path = pdf_path
        self.output_dir = output_dir
        self.dpi = dpi
        self.rotation_deg = rotation_deg
        self._cancelled = False

    def cancel(self):
        """Cancel the conversion process"""
        self._cancelled = True

    def run(self):
        """
        Executes the PDF conversion with progress updates.
        """
        try:
            from pathlib import Path
            
            pdf_path = Path(self.pdf_path)
            output_dir = Path(self.output_dir)
            
            # Create output directory if it doesn't exist
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Announce start
            self.progress.emit(0, f"Opening PDF: {pdf_path.name}")
            try:
                logging.getLogger("pdf").info(
                    f"PDF conversion started | file={pdf_path.name} | dpi={self.dpi} | rotation={self.rotation_deg} | out={output_dir}"
                )
            except Exception:
                pass

            # Build converter and wire callbacks
            converter = PDFToImageConverter(
                output_dir=str(output_dir),
                dpi=self.dpi,
                rotation_deg=self.rotation_deg
            )

            # Callback: per-page progress
            def on_progress(completed, total):
                if total and total > 0:
                    pct = int(5 + (completed / total) * 95)
                else:
                    pct = 5
                self.progress.emit(pct, f"Converting page {completed}/{total}")

            # Cooperative cancellation check
            def cancellation_check():
                return self._cancelled

            # Run conversion (parallel under the hood)
            image_paths = converter.convert_pdf_to_images(
                str(pdf_path),
                image_format='png',
                rotation_deg=self.rotation_deg,
                on_progress=on_progress,
                on_page_done=None,
                cancellation_check=cancellation_check
            )

            if self._cancelled:
                self.progress.emit(0, "Conversion cancelled by user")
                return

            total_images = len(image_paths)
            if total_images == 0:
                self.error.emit("No images were generated from the PDF")
                return

            self.progress.emit(100, f"Successfully converted {total_images} pages to {total_images} images")
            try:
                logging.getLogger("pdf").info(
                    f"PDF conversion finished | images={total_images} | out={output_dir}"
                )
            except Exception:
                pass

        except Exception as e:
            self.error.emit(f"Conversion failed: {str(e)}")
            try:
                logging.getLogger("pdf").error(f"PDF conversion error: {e}")
            except Exception:
                pass
        finally:
            self.finished.emit()

# --- Print RIP Worker Thread ---
class PrintRipWorker(QObject):
    """
    Worker object to handle RIP printing in a separate thread using the rip_to_print module.
    """
    finished = Signal(bool)  # success
    progress = Signal(int, int, str)  # processed, total, status message
    error = Signal(str)  # error message
    files_discovered = Signal(int)  # number of files found
    connection_status = Signal(bool, str)  # connected?, message

    def __init__(self, rip_folder, num_copies=1, pattern="*.bmp", recursive=False, continuous_mode=False, max_wait_time=300, page_filter=None, host='localhost', port=2000):
        super().__init__()
        self.rip_folder = rip_folder
        self.num_copies = num_copies
        self.pattern = pattern
        self.recursive = recursive
        self.host = host
        self.port = port
        self.continuous_mode = continuous_mode
        self.max_wait_time = max_wait_time
        self.page_filter = page_filter or {'mode': 'all', 'from': None, 'to': None, 'reverse': False, 'odd': False, 'even': False}
        self._cancelled = False
        self.gui_printer = None

    def cancel(self):
        """Cancel the printing process"""
        self._cancelled = True
        if self.gui_printer:
            self.gui_printer.cancel()
    
    def abort_print_server(self):
        """Send abort command to the print server"""
        try:
            logger.warning("PrintRipWorker: Sending abort command to print server...")
            success = abort_print_server_operations(self.host, self.port)
            if success:
                logger.info("PrintRipWorker: Print server abort successful")
                return True
            else:
                logger.error("PrintRipWorker: Print server abort failed")
                return False
        except Exception as e:
            logger.error(f"PrintRipWorker: Abort error: {e}")
            return False

    def run(self):
        """
        Executes the RIP printing with progress updates using the rip_to_print module.
        """
        try:
            # Create GUI printer with configured host and port
            self.gui_printer = GUIRipPrinter(self.host, self.port)
            
            # Define progress callback
            def progress_callback(processed, total, message):
                if not self._cancelled:
                    self.progress.emit(processed, total, message)
            
            # Connect to server
            self.connection_status.emit(False, f"Connecting to {self.gui_printer.host}:{self.gui_printer.port}...")
            if not self.gui_printer.connect():
                self.connection_status.emit(False, "Not connected")
                self.error.emit("Failed to connect to Print Server")
                self.finished.emit(False)
                return
            else:
                self.connection_status.emit(True, f"Connected to {self.gui_printer.host}:{self.gui_printer.port}")
            
            # Discover files first to get count
            from pages.rip_to_print.rip_to_print import RIPFolderPrinter
            temp_printer = RIPFolderPrinter(self.gui_printer.client)
            files_with_sizes = temp_printer.discover_rip_files(
                self.rip_folder, 
                pattern=self.pattern, 
                recursive=self.recursive
            )
            
            if not files_with_sizes:
                self.error.emit("No RIP files found in the specified folder")
                self.finished.emit(False)
                return
            
            # Apply page filter
            filtered = self._apply_page_filter(files_with_sizes)
            total_files = len(filtered)
            self.files_discovered.emit(total_files)
            
            # Check for cancellation
            if self._cancelled:
                self.progress.emit(0, total_files, "Printing cancelled by user")
                self.finished.emit(False)
                return
            
            # Print using the module (continuous or normal mode)
            if self.continuous_mode:
                success = self.gui_printer.print_rip_folder_continuous_with_callback(
                    self.rip_folder,
                    progress_callback,
                    pattern=self.pattern,
                    recursive=self.recursive,
                    num_copies=self.num_copies,
                    max_wait_time=self.max_wait_time
                )
            else:
                success = self.gui_printer.print_rip_folder_with_callback(
                    self.rip_folder,
                    progress_callback,
                    pattern=self.pattern,
                    recursive=self.recursive,
                    num_copies=self.num_copies,
                    files_override=filtered
                )
            
            if self._cancelled:
                self.progress.emit(0, total_files, "Printing cancelled by user")
                self.finished.emit(False)
            else:
                self.finished.emit(success)
            
        except Exception as e:
            self.error.emit(f"Printing failed: {str(e)}")
            self.finished.emit(False)
        finally:
            if self.gui_printer:
                try:
                    self.gui_printer.close()
                except:
                    pass

    def _apply_page_filter(self, files_with_sizes):
        """Filter and order files based on page selection rules.
        files_with_sizes: list of (path, size), naturally sorted ascending by name.
        Returns filtered list of same tuples.
        """
        files = list(files_with_sizes)
        # Determine initial ordering
        reverse = bool(self.page_filter.get('reverse'))
        if reverse:
            files = list(reversed(files))

        # Map index to 1-based page numbers in current order
        numbered = list(enumerate(files, start=1))

        mode = self.page_filter.get('mode', 'all')
        f_from = self.page_filter.get('from')
        f_to = self.page_filter.get('to')
        want_odd = bool(self.page_filter.get('odd'))
        want_even = bool(self.page_filter.get('even'))

        def in_range(n):
            if mode != 'range' or f_from is None or f_to is None:
                return True
            lo, hi = min(int(f_from), int(f_to)), max(int(f_from), int(f_to))
            return lo <= n <= hi

        def parity_ok(n):
            if want_odd and want_even:
                return True
            if want_odd:
                return n % 2 == 1
            if want_even:
                return n % 2 == 0
            return True

        filtered = [(p, s) for (idx, (p, s)) in numbered if in_range(idx) and parity_ok(idx)]

        # Log selection summary
        try:
            logging.getLogger("rip_to_print").info(
                f"Page selection | total={len(files_with_sizes)} | selected={len(filtered)} | filter={self.page_filter}"
            )
        except Exception:
            pass

        return filtered

# --- Abort Worker Thread ---
class AbortWorker(QObject):
    """
    Worker object to handle abort operations in a separate thread.
    This prevents the GUI from freezing during abort operations.
    """
    finished = Signal(bool, str)  # success, message
    
    def __init__(self, host='localhost', port=2000):
        super().__init__()
        self.host = host
        self.port = port
        
    def run(self):
        """Execute the abort operation"""
        try:
            logger.warning(f"AbortWorker: Sending abort to {self.host}:{self.port}...")
            success = abort_print_server_operations(self.host, self.port)
            if success:
                message = "Print server aborted successfully"
                logger.info(f"AbortWorker: {message}")
            else:
                message = "Print server abort failed - server may not be responding"
                logger.warning(f"AbortWorker: {message}")
            self.finished.emit(success, message)
        except Exception as e:
            message = f"Abort error: {str(e)}"
            logger.error(f"AbortWorker: {message}")
            self.finished.emit(False, message)

# --- Main GUI Window ---
class MainApplication(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kridwinn Orbit Pro")

        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setStyleSheet(STYLESHEET)
        
        # Get screen dimensions and set window to full screen
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        self.setGeometry(screen_geometry)
        
        # Ensure window is maximized and fills entire screen
        self.showMaximized()
        self.setWindowState(self.windowState() | Qt.WindowMaximized)

        self.current_section = 0  # Track current active section
        self.session_logger = SessionLogger()
        self.session_dir = self.session_logger.get_session_dir()
        
        self._init_ui()

        # Probe server connection on startup (non-blocking)
        try:
            self._probe_server_connection()
        except Exception:
            pass

    def _style_group_box(self, group_box):
        """Apply custom styling to group box titles to make them bigger and bold, positioned close to their own box with proper spacing between sections"""
        try:
            group_box.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    font-size: 12pt;
                    color: #212529;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    margin-top: 20px;
                    padding-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 0px;
                    padding: 0 8px;
                    background: transparent;
                    font-weight: bold;
                    font-size: 12pt;
                    color: #000000;
                }
            """)
        except Exception:
            pass

    def _init_ui(self):
        """
        Initializes the User Interface components.
        """
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Top: Section Navigation Buttons ---
        section_group = QGroupBox("Control Panel")
        self._style_group_box(section_group)
        section_layout = QHBoxLayout()
        
        # Create section buttons
        self.pdf_split_btn = QPushButton("PDF Desk")
        self.pdf_split_btn.setObjectName("SectionButton")
        self.pdf_split_btn.clicked.connect(lambda: self._switch_section(0))

        self.colour_conv_btn = QPushButton("PDF PREP")
        self.colour_conv_btn.setObjectName("SectionButton")
        self.colour_conv_btn.clicked.connect(lambda: self._switch_section(1))

        self.pdf_to_images_btn = QPushButton("RIP Engine")
        self.pdf_to_images_btn.setObjectName("SectionButton")
        self.pdf_to_images_btn.clicked.connect(lambda: self._switch_section(2))
        
        self.images_to_rip_btn = QPushButton("Images to RIP")
        self.images_to_rip_btn.setObjectName("SectionButton")
        self.images_to_rip_btn.clicked.connect(lambda: self._switch_section(3))
        self.images_to_rip_btn.setVisible(False)
        
        self.print_rip_btn = QPushButton("Print the RIP")
        self.print_rip_btn.setObjectName("SectionButton")
        self.print_rip_btn.clicked.connect(lambda: self._switch_section(4))
        self.print_rip_btn.setVisible(False)
        
        self.consolidated_btn = QPushButton("PDF-IMG-RIP-PRINT")
        self.consolidated_btn.setObjectName("SectionButton")
        self.consolidated_btn.clicked.connect(lambda: self._switch_section(5))
        self.consolidated_btn.setVisible(False)
        
        self.build_csv_btn = QPushButton("BUILD CSV")
        self.build_csv_btn.setObjectName("SectionButton")
        self.build_csv_btn.clicked.connect(lambda: self._switch_section(6))
        
        self.multi_server_btn = QPushButton("PRINT ENGINE (GIS)")
        self.multi_server_btn.setObjectName("SectionButton")
        self.multi_server_btn.clicked.connect(lambda: self._switch_section(8))
        
        self.server_config_btn = QPushButton("GIS SERVER CONFIG")
        self.server_config_btn.setObjectName("SectionButton")
        self.server_config_btn.clicked.connect(lambda: self._switch_section(9))
        
        # Add buttons to layout with equal distribution
        section_layout.addStretch()  # Left stretch
        section_layout.addWidget(self.pdf_split_btn, 1)  # Equal stretch factor
        section_layout.addWidget(self.colour_conv_btn, 1)
        section_layout.addWidget(self.pdf_to_images_btn, 1)
        section_layout.addWidget(self.images_to_rip_btn, 1)
        section_layout.addWidget(self.print_rip_btn, 1)
        section_layout.addWidget(self.multi_server_btn, 1)
        section_layout.addWidget(self.server_config_btn, 1)
        section_layout.addWidget(self.consolidated_btn, 1)
        section_layout.addWidget(self.build_csv_btn, 1)
        section_layout.addStretch()  # Right stretch

        # Connection status backend code remains active (no GUI indicator)
        
        section_group.setLayout(section_layout)
        main_layout.addWidget(section_group)

        # --- Main Content Area: Stacked Widget for different sections ---
        self.stacked_widget = QStackedWidget()
        
        # Create content for each section
        self._create_pdf_split_section()
        self._create_pdf_colour_section()
        self._create_pdf_to_images_section()
        self._create_images_to_rip_section()
        self._create_print_rip_section()
        try:
            from pages.pdf_img_rip_print.section import PDFImgRipPrintSection
            self.stacked_widget.addWidget(PDFImgRipPrintSection())
        except Exception as e:
            fallback = QWidget()
            _v = QVBoxLayout(fallback)
            _v.addWidget(QLabel(f"Consolidated section failed to load: {e}"))
            self.stacked_widget.addWidget(fallback)
        
        # BUILD CSV section
        try:
            from pages.build_csv.build_csv_section import BuildCSVSection
            self.stacked_widget.addWidget(BuildCSVSection())
        except Exception as e:
            fallback = QWidget()
            _v = QVBoxLayout(fallback)
            _v.addWidget(QLabel(f"BUILD CSV section failed to load: {e}"))
            self.stacked_widget.addWidget(fallback)
        
        # PAGE IMPOSE section
        try:
            self.page_impose_widget = PageImposeSection()
            self.stacked_widget.addWidget(self.page_impose_widget)
        except Exception as e:
            fallback = QWidget()
            _v = QVBoxLayout(fallback)
            _v.addWidget(QLabel(f"PAGE IMPOSE section failed to load: {e}"))
            self.stacked_widget.addWidget(fallback)
        
        # MULTI-SERVER PRINT section
        try:
            self.multi_server_widget = MultiServerPrintSection()
            self.stacked_widget.addWidget(self.multi_server_widget)
        except Exception as e:
            fallback = QWidget()
            _v = QVBoxLayout(fallback)
            _v.addWidget(QLabel(f"MULTI-SERVER PRINT section failed to load: {e}"))
            self.stacked_widget.addWidget(fallback)
        
        # PRINT SERVER CONFIG section
        try:
            self.server_config_widget = PrintServerConfigSection(parent=self, multi_server_section=self.multi_server_widget)
            self.stacked_widget.addWidget(self.server_config_widget)
        except Exception as e:
            fallback = QWidget()
            _v = QVBoxLayout(fallback)
            _v.addWidget(QLabel(f"PRINT SERVER CONFIG section failed to load: {e}"))
            self.stacked_widget.addWidget(fallback)
        
        main_layout.addWidget(self.stacked_widget, 1)

        # --- Bottom: Quit Button ---
        self.quit_button = QPushButton("Quit Application")
        self.quit_button.setObjectName("SecondaryButton")
        try:
            self.quit_button.setStyleSheet(
                """
                QPushButton { background-color: #dc3545; color: white; font-weight: 600; padding: 8px 14px; border: none; border-radius: 6px; }
                QPushButton:hover { background-color: #c82333; }
                QPushButton:disabled { background-color: #f5c6cb; }
                """
            )
        except Exception:
            pass
        self.quit_button.clicked.connect(self.close)
        main_layout.addWidget(self.quit_button, 0, Qt.AlignRight)

        # Set initial section
        self._switch_section(0)
        # Initialize top indicator state
        try:
            self._set_server_connection_status(False, "Not connected")
        except Exception:
            pass

    def showEvent(self, event):
        """Override showEvent to ensure window is maximized"""
        super().showEvent(event)
        # Force maximized state after showing
        self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def _get_first_server(self):
        """Get the first configured server, or fallback to localhost:2000"""
        try:
            if hasattr(self, 'multi_server_widget') and self.multi_server_widget:
                all_servers = self.multi_server_widget.manager.get_all_servers()
                if all_servers:
                    # get_all_servers() returns a dict, get first server object
                    first_server = next(iter(all_servers.values()))
                    return first_server.ip, first_server.port
        except Exception:
            pass
        # Fallback
        return 'localhost', 2000
    
    def _probe_server_connection(self):
        """Check server availability on app start without blocking UI."""
        try:
            # Get all configured servers from the multi-server section
            servers = []
            if hasattr(self, 'multi_server_widget') and self.multi_server_widget:
                all_servers = self.multi_server_widget.manager.get_all_servers()
                # Extract host:port pairs from configured servers
                # get_all_servers() returns a dict, iterate over values
                for server in all_servers.values():
                    servers.append((server.ip, server.port))
                    
            # Fallback to localhost:2000 if no servers configured
            if not servers:
                servers = [('localhost', 2000)]
                logging.info("No servers configured, using fallback localhost:2000")
            else:
                logging.info(f"Probing {len(servers)} configured server(s): {servers}")
            
            self.conn_probe_thread = QThread()
            self.conn_probe_worker = ConnectionProbeWorker(servers)
            self.conn_probe_worker.moveToThread(self.conn_probe_thread)
            self.conn_probe_thread.started.connect(self.conn_probe_worker.run)
            self.conn_probe_worker.result.connect(self._on_connection_status)
            self.conn_probe_worker.finished.connect(self.conn_probe_thread.quit)
            self.conn_probe_worker.finished.connect(self.conn_probe_worker.deleteLater)
            self.conn_probe_thread.finished.connect(self.conn_probe_thread.deleteLater)
            self.conn_probe_thread.start()
        except Exception as e:
            logging.error(f"Error probing server connection: {e}")
            pass

    def _create_pdf_to_images_section(self):
        """
        Create the PDF Render section (modular), using external PDFRenderSection.
        """
        try:
            self.pdf_render_widget = PDFRenderSection()
            self.stacked_widget.addWidget(self.pdf_render_widget)
        except Exception as e:
            fallback = QWidget()
            layout = QVBoxLayout(fallback)
            layout.addWidget(QLabel(f"PDF Render section failed to load: {e}"))
            self.stacked_widget.addWidget(fallback)

    def _create_pdf_split_section(self):
        """
        Creates the PDF Split section and adds it as the first page in the stack.
        """
        try:
            self.pdf_split_widget = PDFSplitSection()
            self.stacked_widget.addWidget(self.pdf_split_widget)
        except Exception as e:
            # Fallback empty widget if import/creation fails
            fallback = QWidget()
            layout = QVBoxLayout(fallback)
            layout.addWidget(QLabel(f"PDF Split section failed to load: {e}"))
            self.stacked_widget.addWidget(fallback)

    def _create_pdf_colour_section(self):
        """
        Creates the PDF PREP section and adds it as the second page in the stack.
        """
        try:
            self.pdf_colour_widget = PDFColourConversionSection()
            self.stacked_widget.addWidget(self.pdf_colour_widget)
        except Exception as e:
            # Fallback empty widget if import/creation fails
            fallback = QWidget()
            layout = QVBoxLayout(fallback)
            layout.addWidget(QLabel(f"PDF PREP section failed to load: {e}"))
            self.stacked_widget.addWidget(fallback)

    def _select_pdf_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF", os.getcwd(), "PDF Files (*.pdf)")
        if file_path:
            self.pdf_path_edit.setText(file_path)
            self._update_pdf_preview()

    def _get_selected_rotation(self) -> int:
        checked = self.rotation_buttons.checkedId()
        return checked if checked != -1 else 0

    def _update_pdf_preview(self):
        pdf_path = self.pdf_path_edit.text().strip()
        if not pdf_path or not os.path.exists(pdf_path):
            self.preview_label.setText("No PDF selected or file not found")
            return
        try:
            dpi = self.dpi_spin.value()
            rotation = self._get_selected_rotation()
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                self.preview_label.setText("Empty PDF")
                doc.close()
                return
            page = doc[0]
            mat = fitz.Matrix(dpi/72.0, dpi/72.0).prerotate(rotation)
            pix = page.get_pixmap(matrix=mat)
            # Convert to QImage
            if pix.alpha:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888)
            else:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            qimg = qimg.copy()  # Detach from underlying buffer
            pixmap = QPixmap.fromImage(qimg)
            # Scale down to fit nicely in preview
            max_w = self.preview_scroll.width() - 40
            max_h = self.preview_scroll.height() - 40
            if max_w > 0 and max_h > 0:
                pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview_label.setPixmap(pixmap)
            doc.close()
        except Exception as e:
            self.preview_label.setText(f"Preview error: {e}")

    def _start_pdf_conversion(self):
        pdf_path = self.pdf_path_edit.text().strip()
        if not pdf_path or not os.path.exists(pdf_path):
            QMessageBox.warning(self, "PDF Missing", "Please select a valid PDF file.")
            return
        
        dpi = self.dpi_spin.value()
        rotation = self._get_selected_rotation()
        
        # Disable controls during conversion
        self.start_conversion_btn.setEnabled(False)
        self.stop_conversion_btn.setEnabled(True)  # Enable stop button
        self.pdf_browse_btn.setEnabled(False)
        self.dpi_spin.setEnabled(False)
        for btn in [self.rot_0, self.rot_90, self.rot_180, self.rot_270]:
            btn.setEnabled(False)
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_status_label.setText("Starting conversion...")
        
        # Create worker and thread
        self.conversion_thread = QThread()
        self.conversion_worker = PDFConversionWorker(
            pdf_path, str(self.pdf_output_dir), dpi, rotation
        )
        self.conversion_worker.moveToThread(self.conversion_thread)
        
        # Connect signals
        self.conversion_thread.started.connect(self.conversion_worker.run)
        self.conversion_worker.finished.connect(self.conversion_thread.quit)
        self.conversion_worker.finished.connect(self.conversion_worker.deleteLater)
        self.conversion_thread.finished.connect(self.conversion_thread.deleteLater)
        self.conversion_worker.progress.connect(self._update_conversion_progress)
        self.conversion_worker.error.connect(self._handle_conversion_error)
        
        # Re-enable controls when finished
        self.conversion_worker.finished.connect(self._conversion_finished)
        
        # Start the thread
        self.conversion_thread.start()
    
    def _stop_pdf_conversion(self):
        """Stop the current PDF conversion process"""
        if hasattr(self, 'conversion_worker') and self.conversion_worker:
            self.conversion_worker.cancel()
            self.progress_status_label.setText("Stopping conversion...")
            self.stop_conversion_btn.setEnabled(False)
    
    def _update_conversion_progress(self, percentage, message):
        """Update progress bar and status message"""
        self.progress_bar.setValue(percentage)
        self.progress_status_label.setText(message)
    
    def _handle_conversion_error(self, error_message):
        """Handle conversion errors"""
        self.progress_status_label.setText(f"Error: {error_message}")
        self.progress_bar.setValue(0)
        QMessageBox.critical(self, "Conversion Failed", error_message)
        self._conversion_finished()
    
    def _conversion_finished(self):
        """Re-enable controls after conversion"""
        self.start_conversion_btn.setEnabled(True)
        self.stop_conversion_btn.setEnabled(False)  # Disable stop button
        self.pdf_browse_btn.setEnabled(True)
        self.dpi_spin.setEnabled(True)
        for btn in [self.rot_0, self.rot_90, self.rot_180, self.rot_270]:
            btn.setEnabled(True)
        
        # Hide progress bar if conversion was successful
        if self.progress_bar.value() == 100:
            self.progress_bar.setVisible(False)
            self.progress_status_label.setText("Conversion completed successfully!")
            QMessageBox.information(self, "Conversion Complete", 
                                  f"PDF converted successfully!\nImages saved to: {self.pdf_output_dir}")

    def _open_output_folder(self):
        try:
            path = str(self.pdf_output_dir.resolve())
            if os.name == 'nt':
                os.startfile(path)
            elif sys.platform == 'darwin':
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open folder: {e}")

    def _create_images_to_rip_section(self):
        """
        Creates the Images to RIP section.
        """
        self.rip_section_widget = QWidget()
        layout = QHBoxLayout(self.rip_section_widget)

        # Left controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(25)

        # Input folder selection (default to phase_1 output)
        folder_group = QGroupBox("Input Folder (Images)")
        self._style_group_box(folder_group)
        folder_layout = QVBoxLayout()
        self.rip_input_edit = QLineEdit()
        default_input = str(getattr(self, 'pdf_output_dir', Path('phase_1_pdf_to_images')).resolve())
        self.rip_input_edit.setText(default_input)
        self.rip_browse_btn = QPushButton("Browse Folder")
        self.rip_browse_btn.clicked.connect(self._select_rip_input_folder)
        folder_layout.addWidget(self.rip_input_edit)
        folder_layout.addWidget(self.rip_browse_btn)
        folder_group.setLayout(folder_layout)
        controls_layout.addWidget(folder_group)

        # Server Selection group
        server_select_group = QGroupBox("🖥️ GIS Server Selection")
        self._style_group_box(server_select_group)
        server_select_layout = QVBoxLayout()
        
        # Load servers from config
        from pages.multi_server_print.server_manager import PrintServerManager
        self.rip_server_manager = PrintServerManager()
        
        # Server list with checkboxes
        self.rip_server_list = QListWidget()
        self.rip_server_list.setMaximumHeight(150)
        self.rip_server_list.setStyleSheet("""
            QListWidget {
                background-color: #f8f9fa;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }
        """)
        self._load_rip_servers()
        server_select_layout.addWidget(QLabel("Select servers for RIP processing:"))
        server_select_layout.addWidget(self.rip_server_list)
        
        # Distribution mode
        dist_layout = QHBoxLayout()
        dist_layout.addWidget(QLabel("Distribution:"))
        self.rip_distribution_combo = QComboBox()
        self.rip_distribution_combo.addItems(["Alternate (Round-Robin)", "Chunks"])
        self.rip_distribution_combo.setCurrentIndex(0)  # Default to Alternate
        dist_layout.addWidget(self.rip_distribution_combo)
        server_select_layout.addLayout(dist_layout)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Servers")
        refresh_btn.clicked.connect(self._refresh_rip_servers)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        server_select_layout.addWidget(refresh_btn)
        
        server_select_group.setLayout(server_select_layout)
        controls_layout.addWidget(server_select_group)

        # Progress group
        rip_progress_group = QGroupBox("RIP Progress")
        self._style_group_box(rip_progress_group)
        rip_progress_layout = QVBoxLayout()
        self.rip_progress_bar = QProgressBar()
        self.rip_progress_bar.setVisible(False)
        self.rip_status_label = QLabel("Ready to start RIP")
        self.rip_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        rip_progress_layout.addWidget(self.rip_progress_bar)
        rip_progress_layout.addWidget(self.rip_status_label)
        rip_progress_group.setLayout(rip_progress_layout)
        controls_layout.addWidget(rip_progress_group)

        # Action buttons
        actions_group = QGroupBox("Actions")
        self._style_group_box(actions_group)
        actions_layout = QVBoxLayout()
        self.rip_start_btn = QPushButton("Start RIP")
        self.rip_start_btn.clicked.connect(self._start_rip_processing)
        self.rip_stop_btn = QPushButton("STOP")
        self.rip_stop_btn.setObjectName("StopButton")
        self.rip_stop_btn.setEnabled(False)
        self.rip_stop_btn.clicked.connect(self._stop_rip_processing)
        self.rip_open_output_btn = QPushButton("Open RIP Output Folder")
        self.rip_open_output_btn.clicked.connect(self._open_rip_output_folder)
        actions_layout.addWidget(self.rip_start_btn)
        actions_layout.addWidget(self.rip_stop_btn)
        actions_layout.addWidget(self.rip_open_output_btn)
        actions_group.setLayout(actions_layout)
        controls_layout.addWidget(actions_group)

        controls_layout.addStretch()
        # Make left controls scrollable to align with other sections
        try:
            left_scroll = QScrollArea()
            left_scroll.setWidgetResizable(True)
            left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            left_scroll.setWidget(controls_widget)
            left_scroll.setMinimumWidth(320)
            layout.addWidget(left_scroll, 0)
        except Exception:
            layout.addWidget(controls_widget, 0)

        # Right Preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        rip_preview_group = QGroupBox("RIP Preview (Live)")
        self._style_group_box(rip_preview_group)
        rip_preview_layout = QVBoxLayout()
        # Use QListWidget to preview thumbnails
        self.rip_preview_list = QListWidget()
        self.rip_preview_list.setViewMode(QListView.IconMode)
        self.rip_preview_list.setIconSize(QSize(160, 160))
        self.rip_preview_list.setResizeMode(QListView.Adjust)
        self.rip_preview_list.setSpacing(10)
        rip_preview_layout.addWidget(self.rip_preview_list)
        rip_preview_group.setLayout(rip_preview_layout)
        preview_layout.addWidget(rip_preview_group)

        layout.addWidget(preview_widget, 1)
        layout.setStretch(0, 3)
        layout.setStretch(1, 7)

        # RIP output directory
        self.rip_output_dir = Path("rip_output")
        self.rip_output_dir.mkdir(parents=True, exist_ok=True)

        self.stacked_widget.addWidget(self.rip_section_widget)

    def _create_print_rip_section(self):
        """
        Creates the Print RIP section.
        """
        self.print_section_widget = QWidget()
        layout = QHBoxLayout(self.print_section_widget)
        
        # Left side: Controls
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)
        controls_layout.setSpacing(25)
        
        # RIP folder selection
        folder_group = QGroupBox("RIP Folder Selection")
        self._style_group_box(folder_group)
        try:
            folder_group.setMaximumWidth(428)
        except Exception:
            pass
        folder_layout = QVBoxLayout()
        self.print_rip_folder_edit = QLineEdit()
        # Default to rip_output folder from the second stage
        default_rip_folder = str(Path("rip_output").resolve())
        self.print_rip_folder_edit.setText(default_rip_folder)
        self.print_rip_folder_edit.setPlaceholderText("Select RIP folder containing .bmp files...")
        self.print_rip_browse_btn = QPushButton("Browse RIP Folder")
        self.print_rip_browse_btn.clicked.connect(self._select_print_rip_folder)
        folder_layout.addWidget(self.print_rip_folder_edit)
        folder_layout.addWidget(self.print_rip_browse_btn)
        folder_group.setLayout(folder_layout)
        controls_layout.addWidget(folder_group)
        
        # Print settings
        settings_group = QGroupBox("Print Settings")
        self._style_group_box(settings_group)
        try:
            settings_group.setMaximumWidth(428)
        except Exception:
            pass
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(15)  # Add spacing between elements
        
        # Number of copies
        copies_label = QLabel("Number of copies per file:")
        self.print_copies_spin = QSpinBox()
        self.print_copies_spin.setRange(1, 100)
        self.print_copies_spin.setValue(1)
        settings_layout.addWidget(copies_label)
        settings_layout.addWidget(self.print_copies_spin)
        
        # File pattern
        pattern_label = QLabel("File pattern:")
        self.print_pattern_combo = QComboBox()
        self.print_pattern_combo.addItems(["*.bmp", "*.BMP", "*.*"])
        self.print_pattern_combo.setCurrentText("*.bmp")
        settings_layout.addWidget(pattern_label)
        settings_layout.addWidget(self.print_pattern_combo)
        
        # Recursive option
        self.print_recursive_checkbox = QCheckBox("Include subdirectories")
        self.print_recursive_checkbox.setChecked(False)
        settings_layout.addWidget(self.print_recursive_checkbox)
        
        # Page selection controls
        page_sel_group = QGroupBox("Page Selection")
        self._style_group_box(page_sel_group)
        try:
            page_sel_group.setCheckable(False)
            page_sel_group.setEnabled(True)
        except Exception:
            pass
        page_sel_layout = QVBoxLayout()
        page_sel_layout.setSpacing(10)  # Add spacing between elements in Page Selection
        # Mode radios (mutually exclusive)
        self.opt_all_pages = QRadioButton("Print all pages")
        self.opt_all_pages.setChecked(True)
        self.opt_range = QRadioButton("Print range")
        self.chk_odd = QRadioButton("Odd only")
        self.chk_even = QRadioButton("Even only")

        # Group for exclusive selection among modes
        try:
            self.page_mode_group = QButtonGroup(self)
            self.page_mode_group.setExclusive(True)
            self.page_mode_group.addButton(self.opt_all_pages)
            self.page_mode_group.addButton(self.opt_range)
            self.page_mode_group.addButton(self.chk_odd)
            self.page_mode_group.addButton(self.chk_even)
        except Exception:
            pass

        self.range_from = QSpinBox()
        self.range_from.setRange(1, 1000000)
        self.range_to = QSpinBox()
        self.range_to.setRange(1, 1000000)
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("From"))
        range_row.addWidget(self.range_from)
        range_row.addWidget(QLabel("to"))
        range_row.addWidget(self.range_to)
        # Reverse as independent checkbox
        self.chk_reverse = QCheckBox("Reverse order")
        try:
            self.chk_reverse.setTristate(False)
            self.chk_reverse.setEnabled(True)
            self.chk_reverse.setFocusPolicy(Qt.StrongFocus)
            self.chk_reverse.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.chk_reverse.setMinimumSize(20, 20)
            try:
                self.chk_reverse.raise_()
            except Exception:
                pass
            try:
                self.chk_reverse.setCursor(Qt.PointingHandCursor)
            except Exception:
                pass
        except Exception:
            pass
        odd_even_row = QHBoxLayout()
        odd_even_row.addWidget(self.chk_odd)
        odd_even_row.addWidget(self.chk_even)
        # Layout ordering: modes, range row, odd/even row, then reverse
        page_sel_layout.addWidget(self.opt_all_pages)
        page_sel_layout.addWidget(self.opt_range)
        page_sel_layout.addLayout(range_row)
        page_sel_layout.addLayout(odd_even_row)
        page_sel_layout.addWidget(self.chk_reverse)
        page_sel_group.setLayout(page_sel_layout)
        settings_layout.addWidget(page_sel_group)

        # Enable range fields only when range is selected
        try:
            def _update_page_mode_controls():
                want_range = self.opt_range.isChecked()
                self.range_from.setEnabled(want_range)
                self.range_to.setEnabled(want_range)
            _update_page_mode_controls()
            self.opt_all_pages.toggled.connect(_update_page_mode_controls)
            self.opt_range.toggled.connect(_update_page_mode_controls)
            self.chk_odd.toggled.connect(_update_page_mode_controls)
            self.chk_even.toggled.connect(_update_page_mode_controls)
            # Reflect reverse state live in status label to verify clicks register
            try:
                def _on_reverse_toggled(state):
                    txt = "Reverse ON" if state else "Reverse OFF"
                    if hasattr(self, 'print_status_label'):
                        self.print_status_label.setText(f"{self.print_status_label.text().split(' | ')[0]} | {txt}")
                self.chk_reverse.toggled.connect(_on_reverse_toggled)
            except Exception:
                pass
        except Exception:
            pass

        # Continuous printing option
        self.print_continuous_checkbox = QCheckBox("🔄 Continuous Mode (Monitor for new files)")
        self.print_continuous_checkbox.setChecked(False)
        self.print_continuous_checkbox.setToolTip("Continuously monitor folder for new files and add them to print queue automatically")
        settings_layout.addWidget(self.print_continuous_checkbox)
        
        # Max wait time for continuous mode
        wait_label = QLabel("Max wait time for new files (seconds):")
        self.print_max_wait_spin = QSpinBox()
        self.print_max_wait_spin.setRange(30, 3600)
        self.print_max_wait_spin.setValue(300)  # 5 minutes default
        self.print_max_wait_spin.setSuffix(" sec")
        self.print_max_wait_spin.setEnabled(False)  # Disabled by default
        settings_layout.addWidget(wait_label)
        settings_layout.addWidget(self.print_max_wait_spin)
        
        # Connect continuous checkbox to enable/disable wait time
        self.print_continuous_checkbox.toggled.connect(self.print_max_wait_spin.setEnabled)
        
        settings_group.setLayout(settings_layout)
        controls_layout.addWidget(settings_group)
        
        # Progress group
        print_progress_group = QGroupBox("Print Progress")
        self._style_group_box(print_progress_group)
        try:
            print_progress_group.setMaximumWidth(428)
        except Exception:
            pass
        print_progress_layout = QVBoxLayout()
        self.print_progress_bar = QProgressBar()
        self.print_progress_bar.setVisible(False)
        self.print_status_label = QLabel("Ready to start printing")
        self.print_status_label.setStyleSheet("color: #6c757d; font-style: italic;")
        print_progress_layout.addWidget(self.print_progress_bar)
        print_progress_layout.addWidget(self.print_status_label)
        print_progress_group.setLayout(print_progress_layout)
        controls_layout.addWidget(print_progress_group)
        
        # Action buttons
        print_actions_group = QGroupBox("Actions")
        self._style_group_box(print_actions_group)
        try:
            print_actions_group.setMaximumWidth(428)
        except Exception:
            pass
        print_actions_layout = QVBoxLayout()
        self.print_start_btn = QPushButton("Start Printing")
        self.print_start_btn.clicked.connect(self._start_print_processing)
        self.print_stop_btn = QPushButton("🛑 STOP PRINT SERVER")
        self.print_stop_btn.setObjectName("StopButton")
        self.print_stop_btn.setEnabled(False)
        self.print_stop_btn.clicked.connect(self._stop_print_processing)
        self.print_open_folder_btn = QPushButton("Open RIP Folder")
        self.print_open_folder_btn.clicked.connect(self._open_print_rip_folder)
        print_actions_layout.addWidget(self.print_start_btn)
        print_actions_layout.addWidget(self.print_stop_btn)
        print_actions_layout.addWidget(self.print_open_folder_btn)
        print_actions_group.setLayout(print_actions_layout)
        controls_layout.addWidget(print_actions_group)
        
        controls_layout.addStretch()
        
        # Make entire left controls area scrollable
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setWidget(controls_widget)
        left_scroll.setMinimumWidth(320)
        
        layout.addWidget(left_scroll, 0)
        
        # Right side: Preview/Status
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        
        # Print status preview
        print_preview_group = QGroupBox("Print Status")
        self._style_group_box(print_preview_group)
        print_preview_layout = QVBoxLayout()
        
        # Status text area
        self.print_status_text = QTextEdit()
        self.print_status_text.setReadOnly(True)
        self.print_status_text.setMaximumHeight(200)
        self.print_status_text.setPlaceholderText("Print status and progress will appear here...")
        print_preview_layout.addWidget(self.print_status_text)
        
        # File count display
        self.print_file_count_label = QLabel("Files to print: 0")
        self.print_file_count_label.setStyleSheet("font-weight: bold; color: #007bff;")
        print_preview_layout.addWidget(self.print_file_count_label)
        
        # Continuous mode indicator
        self.print_continuous_indicator = QLabel("")
        self.print_continuous_indicator.setStyleSheet("font-weight: bold; color: #28a745; font-size: 12pt;")
        self.print_continuous_indicator.setVisible(False)
        print_preview_layout.addWidget(self.print_continuous_indicator)
        
        print_preview_group.setLayout(print_preview_layout)
        preview_layout.addWidget(print_preview_group)
        
        # Print server info
        server_info_group = QGroupBox("Print Server Information")
        self._style_group_box(server_info_group)
        server_info_layout = QVBoxLayout()

        self.server_info_text = QTextEdit()
        self.server_info_text.setReadOnly(True)
        self.server_info_text.setMaximumHeight(150)
        self.server_info_text.setPlaceholderText("Print server connection status will appear here...")
        server_info_layout.addWidget(self.server_info_text)
        
        server_info_group.setLayout(server_info_layout)
        preview_layout.addWidget(server_info_group)
        
        layout.addWidget(preview_widget, 1)
        
        # Set proportions (30% controls, 70% preview) for consistency
        layout.setStretch(0, 3)
        layout.setStretch(1, 7)
        
        self.stacked_widget.addWidget(self.print_section_widget)

    def _create_consolidated_section(self):
        pass

    def _set_server_connection_status(self, connected: bool, message: str):
        try:
            # Update only the top-right indicator and label
            if hasattr(self, 'top_status_light'):
                if connected:
                    self.top_status_light.setStyleSheet("border-radius: 6px; background-color: #28a745; border: 1px solid #1e7e34;")
                else:
                    self.top_status_light.setStyleSheet("border-radius: 6px; background-color: #dc3545; border: 1px solid #b02a37;")
            if hasattr(self, 'top_status_label'):
                if connected:
                    self.top_status_label.setStyleSheet("font-weight: bold; color: #28a745;")
                else:
                    self.top_status_label.setStyleSheet("font-weight: bold; color: #dc3545;")
                self.top_status_label.setText(message)
        except Exception:
            pass

    # --- Consolidated Section Handlers ---
    def _select_consolidated_pdf_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF", os.getcwd(), "PDF Files (*.pdf)")
        if file_path:
            self.consolidated_pdf_path_edit.setText(file_path)
            self._update_consolidated_pdf_preview()

    def _update_consolidated_pdf_preview(self):
        pdf_path = self.consolidated_pdf_path_edit.text().strip()
        if not pdf_path or not os.path.exists(pdf_path):
            self.consolidated_preview_label.setText("No PDF selected or file not found")
            self.consolidated_preview_file_label.setText("No PDF selected")
            return
        try:
            dpi = self.consolidated_dpi_spin.value()
            rotation_text = self.consolidated_rotation_combo.currentText()
            rotation = int(rotation_text.replace('°', ''))
            
            self.consolidated_preview_file_label.setText(os.path.basename(pdf_path))
            
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                self.consolidated_preview_label.setText("Empty PDF")
                doc.close()
                return
            page = doc[0]
            mat = fitz.Matrix(dpi/72.0, dpi/72.0).prerotate(rotation)
            pix = page.get_pixmap(matrix=mat)
            # Convert to QImage
            if pix.alpha:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888)
            else:
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            qimg = qimg.copy()  # Detach from underlying buffer
            pixmap = QPixmap.fromImage(qimg)
            # Scale down to fit nicely in preview
            max_w = self.consolidated_preview_scroll.width() - 40
            max_h = self.consolidated_preview_scroll.height() - 40
            if max_w > 0 and max_h > 0:
                pixmap = pixmap.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.consolidated_preview_label.setPixmap(pixmap)
            doc.close()
        except Exception as e:
            self.consolidated_preview_label.setText(f"Preview error: {e}")

    def _start_consolidated_pdf_conversion(self):
        pdf_path = self.consolidated_pdf_path_edit.text().strip()
        if not pdf_path or not os.path.exists(pdf_path):
            QMessageBox.warning(self, "PDF Missing", "Please select a valid PDF file.")
            return
        
        dpi = self.consolidated_dpi_spin.value()
        rotation_text = self.consolidated_rotation_combo.currentText()
        rotation = int(rotation_text.replace('°', ''))
        
        # Disable controls during conversion
        self.consolidated_pdf_convert_btn.setEnabled(False)
        self.consolidated_pdf_browse_btn.setEnabled(False)
        self.consolidated_dpi_spin.setEnabled(False)
        self.consolidated_rotation_combo.setEnabled(False)
        
        # Show progress bar
        self.consolidated_progress_bar.setVisible(True)
        self.consolidated_progress_bar.setValue(0)
        self.consolidated_status_label.setText("Starting PDF conversion...")
        
        # Create worker and thread
        self.consolidated_conversion_thread = QThread()
        self.consolidated_conversion_worker = PDFConversionWorker(
            pdf_path, str(self.consolidated_pdf_output_dir), dpi, rotation
        )
        self.consolidated_conversion_worker.moveToThread(self.consolidated_conversion_thread)
        
        # Connect signals
        self.consolidated_conversion_thread.started.connect(self.consolidated_conversion_worker.run)
        self.consolidated_conversion_worker.finished.connect(self.consolidated_conversion_thread.quit)
        self.consolidated_conversion_worker.finished.connect(self.consolidated_conversion_worker.deleteLater)
        self.consolidated_conversion_thread.finished.connect(self.consolidated_conversion_thread.deleteLater)
        self.consolidated_conversion_worker.progress.connect(self._update_consolidated_conversion_progress)
        self.consolidated_conversion_worker.error.connect(self._handle_consolidated_conversion_error)
        self.consolidated_conversion_worker.finished.connect(self._consolidated_conversion_finished)
        
        # Start the thread
        self.consolidated_conversion_thread.start()

    def _update_consolidated_conversion_progress(self, percentage, message):
        """Update progress bar and status message"""
        self.consolidated_progress_bar.setValue(percentage)
        self.consolidated_status_label.setText(message)

    def _handle_consolidated_conversion_error(self, error_message):
        """Handle conversion errors"""
        self.consolidated_status_label.setText(f"Error: {error_message}")
        self.consolidated_progress_bar.setValue(0)
        QMessageBox.critical(self, "Conversion Failed", error_message)
        self._consolidated_conversion_finished()

    def _consolidated_conversion_finished(self):
        """Re-enable controls after conversion"""
        self.consolidated_pdf_convert_btn.setEnabled(True)
        self.consolidated_pdf_browse_btn.setEnabled(True)
        self.consolidated_dpi_spin.setEnabled(True)
        self.consolidated_rotation_combo.setEnabled(True)
        
        # Hide progress bar if conversion was successful
        if self.consolidated_progress_bar.value() == 100:
            self.consolidated_progress_bar.setVisible(False)
            self.consolidated_status_label.setText("PDF conversion completed successfully!")
            QMessageBox.information(self, "Conversion Complete", 
                                  f"PDF converted successfully!\nImages saved to: {self.consolidated_pdf_output_dir}")

    def _select_consolidated_rip_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder", self.consolidated_rip_input_edit.text())
        if folder:
            self.consolidated_rip_input_edit.setText(folder)

    def _start_consolidated_rip_processing(self):
        input_folder = self.consolidated_rip_input_edit.text().strip()
        if not input_folder or not os.path.isdir(input_folder):
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid input folder containing images.")
            return

        # Disable controls
        self.consolidated_rip_btn.setEnabled(False)
        self.consolidated_rip_browse_btn.setEnabled(False)
        self.consolidated_progress_bar.setVisible(True)
        self.consolidated_progress_bar.setValue(0)
        self.consolidated_status_label.setText("Starting RIP processing...")

        # Get configured server
        host, port = self._get_first_server()
        
        # Start worker thread
        self.consolidated_rip_thread = QThread()
        self.consolidated_rip_worker = SimpleRipWorker(
            input_folder=input_folder,
            output_folder=str(self.consolidated_rip_output_dir),
            host=host,
            port=port
        )
        self.consolidated_rip_worker.moveToThread(self.consolidated_rip_thread)

        self.consolidated_rip_thread.started.connect(self.consolidated_rip_worker.run)
        self.consolidated_rip_worker.finished.connect(self.consolidated_rip_thread.quit)
        self.consolidated_rip_worker.finished.connect(self.consolidated_rip_worker.deleteLater)
        self.consolidated_rip_thread.finished.connect(self.consolidated_rip_thread.deleteLater)
        self.consolidated_rip_worker.progress.connect(self._update_consolidated_rip_progress)
        self.consolidated_rip_worker.error.connect(self._consolidated_rip_error)
        self.consolidated_rip_worker.finished.connect(self._consolidated_rip_finished)

        self.consolidated_rip_thread.start()

    def _update_consolidated_rip_progress(self, processed, total, message):
        try:
            percent = int((processed / total) * 100) if total else 0
            self.consolidated_progress_bar.setValue(percent)
            self.consolidated_status_label.setText(message)
        except Exception:
            pass

    def _consolidated_rip_finished(self, success):
        self.consolidated_rip_btn.setEnabled(True)
        self.consolidated_rip_browse_btn.setEnabled(True)
        if self.consolidated_progress_bar.value() == 100 and success:
            self.consolidated_status_label.setText("RIP completed successfully!")
        else:
            self.consolidated_status_label.setText("RIP stopped or completed with errors.")

    def _consolidated_rip_error(self, message):
        QMessageBox.critical(self, "RIP Error", message)
        self._consolidated_rip_finished(False)

    def _select_consolidated_print_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select RIP Folder", self.consolidated_print_folder_edit.text())
        if folder:
            self.consolidated_print_folder_edit.setText(folder)

    def _start_consolidated_print_processing(self):
        rip_folder = self.consolidated_print_folder_edit.text().strip()
        if not rip_folder or not os.path.isdir(rip_folder):
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid RIP folder containing .bmp files.")
            return

        # Get settings
        num_copies = self.consolidated_copies_spin.value()
        continuous_mode = self.consolidated_continuous_checkbox.isChecked()

        # Clear status
        self.consolidated_print_status_text.clear()
        self.consolidated_file_count_label.setText("Files to print: 0")

        # Disable controls
        self.consolidated_print_btn.setEnabled(False)
        self.consolidated_stop_btn.setEnabled(True)
        self.consolidated_print_browse_btn.setEnabled(False)
        self.consolidated_copies_spin.setEnabled(False)
        self.consolidated_continuous_checkbox.setEnabled(False)
        
        # Show progress bar
        self.consolidated_progress_bar.setVisible(True)
        self.consolidated_progress_bar.setValue(0)
        
        if continuous_mode:
            self.consolidated_status_label.setText("Starting CONTINUOUS print process...")
            timestamp = time.strftime("%H:%M:%S")
            self.consolidated_print_status_text.append(f"[{timestamp}] 🔄 Starting CONTINUOUS mode - will monitor folder for new files")
        else:
            self.consolidated_status_label.setText("Starting print process...")

        # Build page filter spec (default to all pages)
        page_filter = {
            'mode': 'all',
            'from': None,
            'to': None,
            'reverse': False,
            'odd': False,
            'even': False
        }

        # Get configured server
        host, port = self._get_first_server()
        
        # Start worker thread
        self.consolidated_print_thread = QThread()
        self.consolidated_print_worker = PrintRipWorker(
            rip_folder=rip_folder,
            num_copies=num_copies,
            pattern="*.bmp",
            recursive=False,
            continuous_mode=continuous_mode,
            max_wait_time=300,
            page_filter=page_filter,
            host=host,
            port=port
        )
        self.consolidated_print_worker.moveToThread(self.consolidated_print_thread)

        # Connect signals
        self.consolidated_print_thread.started.connect(self.consolidated_print_worker.run)
        self.consolidated_print_worker.finished.connect(self.consolidated_print_thread.quit)
        self.consolidated_print_worker.finished.connect(self.consolidated_print_worker.deleteLater)
        self.consolidated_print_thread.finished.connect(self.consolidated_print_thread.deleteLater)
        self.consolidated_print_worker.progress.connect(self._update_consolidated_print_progress)
        self.consolidated_print_worker.files_discovered.connect(self._on_consolidated_files_discovered)
        self.consolidated_print_worker.error.connect(self._consolidated_print_error)
        self.consolidated_print_worker.finished.connect(self._consolidated_print_finished)
        self.consolidated_print_worker.connection_status.connect(self._on_consolidated_connection_status)

        # Start the thread
        self.consolidated_print_thread.start()

    def _stop_consolidated_print_processing(self):
        """Stop the print processing and abort print server operations"""
        # Show confirmation dialog
        reply = QMessageBox.question(
            self, 
            'Stop Print Process',
            'Are you sure you want to stop the print process?\n\nThis will send an ABORT command to the print server.',
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        if hasattr(self, 'consolidated_print_worker') and self.consolidated_print_worker:
            # First cancel the worker
            self.consolidated_print_worker.cancel()
            self.consolidated_status_label.setText("Stopping print process...")
            self.consolidated_stop_btn.setEnabled(False)
            
            # Send abort command to print server
            try:
                host, port = self._get_first_server()
                success = abort_print_server_operations(host, port)
                if success:
                    self.consolidated_status_label.setText("Print server aborted successfully")
                    timestamp = time.strftime("%H:%M:%S")
                    self.consolidated_print_status_text.append(f"[{timestamp}] ✅ Print server abort command sent successfully")
                    QMessageBox.information(self, "Abort Successful", "Print server has been aborted successfully.")
                else:
                    self.consolidated_status_label.setText("Print server abort failed")
                    timestamp = time.strftime("%H:%M:%S")
                    self.consolidated_print_status_text.append(f"[{timestamp}] ⚠️ WARNING: Print server abort failed")
                    QMessageBox.warning(self, "Abort Failed", "Failed to abort the print server.")
            except Exception as e:
                self.consolidated_status_label.setText(f"Abort error: {str(e)}")
                timestamp = time.strftime("%H:%M:%S")
                self.consolidated_print_status_text.append(f"[{timestamp}] ❌ ERROR: Abort command failed - {str(e)}")
                QMessageBox.critical(self, "Abort Error", f"Error sending abort command:\n{str(e)}")
            
            # Force finish the print process
            self._consolidated_print_finished(False)

    def _update_consolidated_print_progress(self, processed, total, message):
        try:
            if total > 0:
                percent = int((processed / total) * 100)
                self.consolidated_progress_bar.setValue(percent)
            else:
                self.consolidated_progress_bar.setValue(processed)
            
            self.consolidated_status_label.setText(message)
            
            # Add to status text
            timestamp = time.strftime("%H:%M:%S")
            self.consolidated_print_status_text.append(f"[{timestamp}] {message}")
            
            # Auto-scroll to bottom
            scrollbar = self.consolidated_print_status_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
        except Exception:
            pass

    def _on_consolidated_files_discovered(self, file_count):
        self.consolidated_file_count_label.setText(f"Files to print: {file_count}")

    def _consolidated_print_finished(self, success):
        self.consolidated_print_btn.setEnabled(True)
        self.consolidated_stop_btn.setEnabled(False)
        self.consolidated_print_browse_btn.setEnabled(True)
        self.consolidated_copies_spin.setEnabled(True)
        self.consolidated_continuous_checkbox.setEnabled(True)
        
        if success:
            self.consolidated_status_label.setText("Printing completed successfully!")
            self.consolidated_progress_bar.setValue(100)
            QMessageBox.information(self, "Print Complete", 
                                  "RIP files have been sent to the print server successfully!")
        else:
            self.consolidated_status_label.setText("Printing failed or was cancelled")
            self.consolidated_progress_bar.setValue(0)

    def _consolidated_print_error(self, message):
        self.consolidated_status_label.setText(f"Error: {message}")
        self.consolidated_progress_bar.setValue(0)
        
        # Add error to status text
        timestamp = time.strftime("%H:%M:%S")
        self.consolidated_print_status_text.append(f"[{timestamp}] ERROR: {message}")
        
        QMessageBox.critical(self, "Print Error", message)
        self._consolidated_print_finished(False)

    def _on_consolidated_connection_status(self, connected: bool, message: str):
        try:
            timestamp = time.strftime("%H:%M:%S")
            self.consolidated_print_status_text.append(f"[{timestamp}] {message}")
            self.consolidated_server_info_text.append(f"[{timestamp}] {message}")
        except Exception:
            pass

    def _switch_section(self, section_index):
        """
        Switches to the specified section and updates button states.
        """
        self.current_section = section_index
        
        # Map buttons to their section indices (section 7 has no button - PAGE IMPOSE)
        button_section_map = {
            0: self.pdf_split_btn,
            1: self.colour_conv_btn,
            2: self.pdf_to_images_btn,
            3: self.images_to_rip_btn,
            4: self.print_rip_btn,
            5: self.consolidated_btn,
            6: self.build_csv_btn,
            8: self.multi_server_btn,  # Section 7 (PAGE IMPOSE) has no button, so multi-server is at index 8
            9: self.server_config_btn   # Server config at index 9
        }
        
        # Update all button states
        for sec_idx, button in button_section_map.items():
            if sec_idx == section_index:
                button.setProperty("active", True)
                button.style().unpolish(button)
                button.style().polish(button)
            else:
                button.setProperty("active", False)
                button.style().unpolish(button)
                button.style().polish(button)
        
        # Switch to the corresponding widget
        self.stacked_widget.setCurrentIndex(section_index)

    # --- Images to RIP handlers ---
    def _select_rip_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder", self.rip_input_edit.text())
        if folder:
            self.rip_input_edit.setText(folder)
    
    def _load_rip_servers(self):
        """Load servers from config and populate list with checkboxes"""
        self.rip_server_list.clear()
        servers = self.rip_server_manager.get_all_servers()
        
        for server_id, config in servers.items():
            if not config.enabled:
                continue  # Skip disabled servers
            
            item = QListWidgetItem()
            checkbox = QCheckBox(f"{config.name} ({config.ip}:{config.port})")
            checkbox.setChecked(True)  # Default to checked
            checkbox.setProperty("server_id", server_id)
            checkbox.setProperty("server_config", config)
            
            self.rip_server_list.addItem(item)
            self.rip_server_list.setItemWidget(item, checkbox)
        
        if self.rip_server_list.count() == 0:
            item = QListWidgetItem("⚠️ No servers configured. Go to GIS SERVER CONFIG.")
            self.rip_server_list.addItem(item)
    
    def _refresh_rip_servers(self):
        """Refresh server list from configuration file"""
        self.rip_server_manager = PrintServerManager()  # Reload from file
        self._load_rip_servers()
        QMessageBox.information(self, "Servers Refreshed", "Server list has been refreshed from configuration.")
    
    def _get_selected_rip_servers(self):
        """Get list of selected server configurations"""
        selected_servers = []
        
        for i in range(self.rip_server_list.count()):
            item = self.rip_server_list.item(i)
            widget = self.rip_server_list.itemWidget(item)
            
            if isinstance(widget, QCheckBox) and widget.isChecked():
                server_id = widget.property("server_id")
                config = widget.property("server_config")
                
                if server_id and config:
                    selected_servers.append({
                        'id': server_id,
                        'host': config.ip,
                        'port': config.port,
                        'name': config.name
                    })
        
        return selected_servers

    def _start_rip_processing(self):
        input_folder = self.rip_input_edit.text().strip()
        if not input_folder or not os.path.isdir(input_folder):
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid input folder containing images.")
            return
        
        # Get selected servers
        selected_servers = self._get_selected_rip_servers()
        
        if not selected_servers:
            QMessageBox.warning(
                self, "No Servers Selected",
                "Please select at least one server for RIP processing.\n\n"
                "If no servers are available, go to GIS SERVER CONFIG to add them."
            )
            return
        
        # Get distribution mode
        distribution_mode = 'alternate' if self.rip_distribution_combo.currentIndex() == 0 else 'chunks'
        
        try:
            server_names = ", ".join([s['name'] for s in selected_servers])
            logging.getLogger("images_to_rip").info(
                f"Images->RIP started | input={input_folder} | output={self.rip_output_dir} | "
                f"servers={len(selected_servers)} ({server_names}) | mode={distribution_mode}"
            )
        except Exception:
            pass

        # Reset preview
        self.rip_preview_list.clear()

        # Disable controls
        self.rip_start_btn.setEnabled(False)
        self.rip_stop_btn.setEnabled(True)
        self.rip_browse_btn.setEnabled(False)
        self.rip_progress_bar.setVisible(True)
        self.rip_progress_bar.setValue(0)
        
        if len(selected_servers) == 1:
            self.rip_status_label.setText(f"Starting RIP on {selected_servers[0]['name']}...")
        else:
            self.rip_status_label.setText(f"Starting RIP on {len(selected_servers)} servers ({distribution_mode})...")

        # Start worker thread with multi-server support
        self.rip_thread = QThread()
        self.rip_worker = MultiServerRipWorker(
            input_folder=input_folder,
            output_folder=str(self.rip_output_dir),
            server_configs=selected_servers,
            distribution_mode=distribution_mode
        )
        self.rip_worker.moveToThread(self.rip_thread)

        self.rip_thread.started.connect(self.rip_worker.run)
        self.rip_worker.finished.connect(self.rip_thread.quit)
        self.rip_worker.finished.connect(self.rip_worker.deleteLater)
        self.rip_thread.finished.connect(self.rip_thread.deleteLater)
        self.rip_worker.progress.connect(self._update_rip_progress)
        self.rip_worker.image_done.connect(self._on_rip_image_done)
        self.rip_worker.error.connect(self._rip_error)
        self.rip_worker.finished.connect(self._rip_finished)

        self.rip_thread.start()

    def _stop_rip_processing(self):
        if hasattr(self, 'rip_worker') and self.rip_worker:
            self.rip_worker.cancel()
            self.rip_status_label.setText("Stopping RIP...")
            self.rip_stop_btn.setEnabled(False)

    def _update_rip_progress(self, processed, total, message):
        try:
            # Extract progress from messages like "Processed 150/6800 images"
            import re
            match = re.search(r'(\d+)/(\d+)', message)
            if match:
                current = int(match.group(1))
                total_files = int(match.group(2))
                percent = int((current / total_files) * 100)
                self.rip_progress_bar.setValue(percent)
            elif total > 0:
                percent = int((processed / total) * 100)
                self.rip_progress_bar.setValue(percent)
            else:
                self.rip_progress_bar.setValue(processed)
                
            self.rip_status_label.setText(message)
        except Exception:
            pass

    def _on_rip_image_done(self, rip_path):
        try:
            # Load thumbnail
            item = QListWidgetItem()
            pixmap = QPixmap(str(rip_path))
            if not pixmap.isNull():
                item.setIcon(pixmap.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            item.setText(Path(rip_path).name)
            self.rip_preview_list.addItem(item)
        except Exception:
            pass

    def _rip_finished(self, success):
        self.rip_start_btn.setEnabled(True)
        self.rip_stop_btn.setEnabled(False)
        self.rip_browse_btn.setEnabled(True)
        if self.rip_progress_bar.value() == 100 and success:
            self.rip_status_label.setText("RIP completed successfully!")
            try:
                logging.getLogger("images_to_rip").info("Images->RIP finished successfully")
            except Exception:
                pass
        else:
            self.rip_status_label.setText("RIP stopped or completed with errors.")
            try:
                logging.getLogger("images_to_rip").warning("Images->RIP finished with issues")
            except Exception:
                pass

    def _rip_error(self, message):
        QMessageBox.critical(self, "RIP Error", message)
        self._rip_finished(False)
        try:
            logging.getLogger("images_to_rip").error(f"Images->RIP error: {message}")
        except Exception:
            pass

    def _open_rip_output_folder(self):
        try:
            path = str(self.rip_output_dir.resolve())
            if os.name == 'nt':
                os.startfile(path)
            elif sys.platform == 'darwin':
                os.system(f"open '{path}'")
            else:
                os.system(f"xdg-open '{path}'")
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open RIP output folder: {e}")

    # --- Print RIP handlers ---
    def _select_print_rip_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select RIP Folder", self.print_rip_folder_edit.text())
        if folder:
            self.print_rip_folder_edit.setText(folder)

    def _open_print_rip_folder(self):
        try:
            folder_path = self.print_rip_folder_edit.text().strip()
            if folder_path and os.path.exists(folder_path):
                if os.name == 'nt':
                    os.startfile(folder_path)
                elif sys.platform == 'darwin':
                    os.system(f"open '{folder_path}'")
                else:
                    os.system(f"xdg-open '{folder_path}'")
            else:
                QMessageBox.warning(self, "Open Folder", "Please select a valid RIP folder first.")
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open RIP folder: {e}")

    def _start_print_processing(self):
        rip_folder = self.print_rip_folder_edit.text().strip()
        if not rip_folder or not os.path.isdir(rip_folder):
            QMessageBox.warning(self, "Invalid Folder", "Please select a valid RIP folder containing .bmp files.")
            return
        try:
            logging.getLogger("rip_to_print").info(
                f"Print RIP started | folder={rip_folder} | copies={self.print_copies_spin.value()} | pattern={self.print_pattern_combo.currentText()} | recursive={self.print_recursive_checkbox.isChecked()} | continuous={self.print_continuous_checkbox.isChecked()} | max_wait={self.print_max_wait_spin.value()}"
            )
        except Exception:
            pass

        # Get settings
        num_copies = self.print_copies_spin.value()
        pattern = self.print_pattern_combo.currentText()
        recursive = self.print_recursive_checkbox.isChecked()
        continuous_mode = self.print_continuous_checkbox.isChecked()
        max_wait_time = self.print_max_wait_spin.value()

        # Clear status
        self.print_status_text.clear()
        self.print_file_count_label.setText("Files to print: 0")

        # Disable controls
        self.print_start_btn.setEnabled(False)
        self.print_stop_btn.setEnabled(True)
        self.print_stop_btn.setText("🛑 STOP PRINT SERVER")
        self.print_rip_browse_btn.setEnabled(False)
        self.print_copies_spin.setEnabled(False)
        self.print_pattern_combo.setEnabled(False)
        self.print_recursive_checkbox.setEnabled(False)
        self.print_continuous_checkbox.setEnabled(False)
        self.print_max_wait_spin.setEnabled(False)
        
        # Show progress bar
        self.print_progress_bar.setVisible(True)
        self.print_progress_bar.setValue(0)
        
        if continuous_mode:
            self.print_status_label.setText("Starting CONTINUOUS print process...")
            self.print_continuous_indicator.setText("🔄 CONTINUOUS MODE ACTIVE")
            self.print_continuous_indicator.setVisible(True)
            timestamp = time.strftime("%H:%M:%S")
            self.print_status_text.append(f"[{timestamp}] 🔄 Starting CONTINUOUS mode - will monitor folder for new files")
            self.print_status_text.append(f"[{timestamp}] Max wait time: {max_wait_time} seconds")
        else:
            self.print_status_label.setText("Starting print process...")
            self.print_continuous_indicator.setVisible(False)

        # Build page filter spec
        # Build page filter from mutually exclusive modes + independent reverse
        page_filter = {
            'mode': 'all',  # 'all' | 'range' | 'odd' | 'even'
            'from': None,
            'to': None,
            'reverse': self.chk_reverse.isChecked(),
            'odd': False,
            'even': False
        }
        if self.opt_range.isChecked():
            page_filter['mode'] = 'range'
            page_filter['from'] = int(self.range_from.value())
            page_filter['to'] = int(self.range_to.value())
        elif self.chk_odd.isChecked():
            page_filter['mode'] = 'odd'
            page_filter['odd'] = True
        elif self.chk_even.isChecked():
            page_filter['mode'] = 'even'
            page_filter['even'] = True

        try:
            logging.getLogger("rip_to_print").info(f"Page filter: {page_filter}")
        except Exception:
            pass

        # Get configured server
        host, port = self._get_first_server()
        
        # Start worker thread
        self.print_thread = QThread()
        self.print_worker = PrintRipWorker(
            rip_folder=rip_folder,
            num_copies=num_copies,
            pattern=pattern,
            recursive=recursive,
            continuous_mode=continuous_mode,
            max_wait_time=max_wait_time,
            page_filter=page_filter,
            host=host,
            port=port
        )
        self.print_worker.moveToThread(self.print_thread)

        # Connect signals
        self.print_thread.started.connect(self.print_worker.run)
        self.print_worker.finished.connect(self.print_thread.quit)
        self.print_worker.finished.connect(self.print_worker.deleteLater)
        self.print_thread.finished.connect(self.print_thread.deleteLater)
        self.print_worker.progress.connect(self._update_print_progress)
        self.print_worker.files_discovered.connect(self._on_files_discovered)
        self.print_worker.error.connect(self._print_error)
        self.print_worker.finished.connect(self._print_finished)
        # New: connection status updates
        try:
            self.print_worker.connection_status.connect(self._on_connection_status)
        except Exception:
            pass

        # Start the thread
        self.print_thread.start()
        # Reflect initial UI status
        try:
            self._set_server_connection_status(False, "Connecting...")
        except Exception:
            pass

    def _stop_print_processing(self):
        """Stop the print processing and abort print server operations"""
        # Show confirmation dialog
        reply = QMessageBox.question(
            self, 
            'Stop Print Process',
            'Are you sure you want to stop the print process?\n\nThis will send an ABORT command to the print server.',
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        if hasattr(self, 'print_worker') and self.print_worker:
            # First cancel the worker
            self.print_worker.cancel()
            self.print_status_label.setText("Stopping print process...")
            self.print_stop_btn.setEnabled(False)
            try:
                self._set_server_connection_status(False, "Not connected")
            except Exception:
                pass
            
            # Send abort command to print server using AbortWorker (non-blocking)
            timestamp = time.strftime("%H:%M:%S")
            self.print_status_text.append(f"[{timestamp}] 🛑 Sending abort command to print server...")
            logger.warning("GUI: User confirmed STOP - sending abort to print server...")
            
            # Get configured server
            host, port = self._get_first_server()
            
            # Create and start abort worker thread
            self.abort_thread = QThread()
            self.abort_worker = AbortWorker(host, port)
            self.abort_worker.moveToThread(self.abort_thread)
            
            # Connect signals
            self.abort_thread.started.connect(self.abort_worker.run)
            self.abort_worker.finished.connect(self._on_abort_finished)
            self.abort_worker.finished.connect(self.abort_thread.quit)
            self.abort_worker.finished.connect(self.abort_worker.deleteLater)
            self.abort_thread.finished.connect(self.abort_thread.deleteLater)
            
            # Start the abort operation
            self.abort_thread.start()
            
            # Also try to abort via the worker if it has a connection
            try:
                if hasattr(self.print_worker, 'abort_print_server'):
                    worker_abort_success = self.print_worker.abort_print_server()
                    if worker_abort_success:
                        logger.info("GUI: Worker abort also successful")
                    else:
                        logger.warning("GUI: Worker abort failed")
            except Exception as e:
                logger.warning(f"GUI: Worker abort error: {e}")
            
            # Force finish the print process
            self._print_finished(False)
        else:
            # If no worker is running, just send abort to server (non-blocking)
            logger.warning("GUI: No worker running - sending direct abort to print server...")
            timestamp = time.strftime("%H:%M:%S")
            self.print_status_text.append(f"[{timestamp}] 🛑 Sending abort command to print server...")
            
            # Get configured server
            host, port = self._get_first_server()
            
            # Create and start abort worker thread
            self.abort_thread = QThread()
            self.abort_worker = AbortWorker(host, port)
            self.abort_worker.moveToThread(self.abort_thread)
            
            # Connect signals
            self.abort_thread.started.connect(self.abort_worker.run)
            self.abort_worker.finished.connect(self._on_abort_finished)
            self.abort_worker.finished.connect(self.abort_thread.quit)
            self.abort_worker.finished.connect(self.abort_worker.deleteLater)
            self.abort_thread.finished.connect(self.abort_thread.deleteLater)
            
            # Start the abort operation
            self.abort_thread.start()
    
    def _on_abort_finished(self, success, message):
        """Handle abort operation completion"""
        timestamp = time.strftime("%H:%M:%S")
        if success:
            self.print_status_label.setText("Print server aborted successfully")
            self.print_status_text.append(f"[{timestamp}] ✅ {message}")
            logger.info(f"GUI: {message}")
        else:
            self.print_status_label.setText("Print server abort failed")
            self.print_status_text.append(f"[{timestamp}] ⚠️ WARNING: {message}")
            logger.warning(f"GUI: {message}")

    def _update_print_progress(self, processed, total, message):
        try:
            # Extract progress from messages like "Queued 200/7100 files"
            import re
            match = re.search(r'(\d+)/(\d+)', message)
            if match:
                current = int(match.group(1))
                total_files = int(match.group(2))
                percent = int((current / total_files) * 100)
                self.print_progress_bar.setValue(percent)
            elif total > 0:
                percent = int((processed / total) * 100)
                self.print_progress_bar.setValue(percent)
            else:
                self.print_progress_bar.setValue(processed)
            
            self.print_status_label.setText(message)
            timestamp = time.strftime("%H:%M:%S")
            self.print_status_text.append(f"[{timestamp}] {message}")
            
            # Auto-scroll to bottom
            scrollbar = self.print_status_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            
        except Exception:
            pass

    def _on_files_discovered(self, file_count):
        self.print_file_count_label.setText(f"Files to print: {file_count}")

    def _print_finished(self, success):
        self.print_start_btn.setEnabled(True)
        self.print_stop_btn.setEnabled(False)
        self.print_stop_btn.setText("🛑 STOP PRINT SERVER")
        self.print_rip_browse_btn.setEnabled(True)
        self.print_copies_spin.setEnabled(True)
        self.print_pattern_combo.setEnabled(True)
        self.print_recursive_checkbox.setEnabled(True)
        self.print_continuous_checkbox.setEnabled(True)
        self.print_continuous_indicator.setVisible(False)
        # Note: max_wait_time will be enabled/disabled based on continuous checkbox state
        
        if success:
            self.print_status_label.setText("Printing completed successfully!")
            self.print_progress_bar.setValue(100)
            QMessageBox.information(self, "Print Complete", 
                                  "RIP files have been sent to the print server successfully!")
            try:
                logging.getLogger("rip_to_print").info("Print RIP finished successfully")
            except Exception:
                pass
        else:
            self.print_status_label.setText("Printing failed or was cancelled")
            self.print_progress_bar.setValue(0)
            try:
                logging.getLogger("rip_to_print").warning("Print RIP finished with issues")
            except Exception:
                pass
        # Do not force disconnect here; reflect that job is done

    def _print_error(self, message):
        self.print_status_label.setText(f"Error: {message}")
        self.print_progress_bar.setValue(0)
        
        # Add error to status text
        timestamp = time.strftime("%H:%M:%S")
        self.print_status_text.append(f"[{timestamp}] ERROR: {message}")
        try:
            self._set_server_connection_status(False, "Not connected")
        except Exception:
            pass
        try:
            logging.getLogger("rip_to_print").error(f"Print RIP error: {message}")
        except Exception:
            pass
        
        QMessageBox.critical(self, "Print Error", message)
        self._print_finished(False)

    def _on_connection_status(self, connected: bool, message: str):
        try:
            self._set_server_connection_status(connected, message)
            timestamp = time.strftime("%H:%M:%S")
            self.print_status_text.append(f"[{timestamp}] {message}")
        except Exception:
            pass
        try:
            logging.getLogger("connection").info(message)
        except Exception:
            pass


class ConnectionProbeWorker(QObject):
    """Lightweight connector that probes server connectivity once on startup."""
    finished = Signal()
    result = Signal(bool, str)

    def __init__(self, servers):
        """
        Initialize with a list of (host, port) tuples.
        
        Args:
            servers: List of (host, port) tuples to probe
        """
        super().__init__()
        self.servers = servers

    def run(self):
        """Probe all configured servers and report connectivity status."""
        connected_servers = []
        failed_servers = []
        
        for host, port in self.servers:
            try:
                logging.info(f"Probing server {host}:{port}...")
                client = GUIRipPrinter(host, port)
                if client.connect():
                    connected_servers.append(f"{host}:{port}")
                    logging.info(f"✅ Server {host}:{port} is reachable")
                    try:
                        client.close()
                    except Exception:
                        pass
                else:
                    failed_servers.append(f"{host}:{port}")
                    logging.warning(f"❌ Server {host}:{port} connection failed")
            except Exception as e:
                failed_servers.append(f"{host}:{port}")
                logging.warning(f"❌ Server {host}:{port} error: {e}")
        
        # Emit result with detailed connection status
        if connected_servers:
            if len(connected_servers) == len(self.servers):
                # All servers connected
                ports_str = ", ".join(connected_servers)
                logging.info(f"All {len(self.servers)} server(s) connected successfully")
                self.result.emit(True, f"Connected: {ports_str}")
            else:
                # Some servers connected
                ports_str = ", ".join(connected_servers)
                logging.warning(f"Only {len(connected_servers)}/{len(self.servers)} server(s) connected")
                self.result.emit(True, f"Connected: {ports_str}")
        else:
            # No servers connected
            logging.error("No servers are reachable")
            self.result.emit(False, "Not connected")
        
        self.finished.emit()

    def _open_print_rip_folder(self):
        try:
            folder_path = self.print_rip_folder_edit.text().strip()
            if folder_path and os.path.exists(folder_path):
                if os.name == 'nt':
                    os.startfile(folder_path)
                elif sys.platform == 'darwin':
                    os.system(f"open '{folder_path}'")
                else:
                    os.system(f"xdg-open '{folder_path}'")
            else:
                QMessageBox.warning(self, "Open Folder", "Please select a valid RIP folder first.")
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open RIP folder: {e}")


# --- Simple RIP Worker (exactly like original code) ---
class SimpleRipWorker(QObject):
    finished = Signal(bool)
    error = Signal(str)
    progress = Signal(int, int, str)  # processed, total, message
    image_done = Signal(str)  # rip file path

    def __init__(self, input_folder: str, output_folder: str, host='localhost', port=2000):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.host = host
        self.port = port
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            # Use configured host and port
            NUM_CONNECTIONS = 10     # Start higher
            MAX_WORKERS = 8          # Start with 8, can adapt up to 12
            DELAY_BETWEEN_SUBMISSIONS = 0.2
            
            client_pool = ClientPool(self.host, self.port, pool_size=NUM_CONNECTIONS)
            if not client_pool.initialize():
                self.error.emit("Failed to connect to Print Server")
                self.finished.emit(False)
                return

            processor = ParallelImageRipProcessor(
                client_pool, 
                output_dir=self.output_folder,
                max_workers=MAX_WORKERS
            )
            
            # Pass cancellation flag to processor
            processor.set_cancellation_callback(lambda: self._cancelled)
            
            # Get total count first
            from pathlib import Path
            folder_path = Path(self.input_folder)
            image_files = []
            SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
            for file_path in folder_path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    image_files.append(file_path)
            total_count = len(image_files)
            
            # Monitor progress with cancellation check and adaptive feedback
            import threading
            def monitor_progress():
                last_count = 0
                last_worker_count = MAX_WORKERS
                
                while not self._cancelled:
                    if self._cancelled:  # Check again before processing
                        processor.cancel_processing()
                        break
                        
                    current_count = processor.processed_count
                    current_workers = processor.get_current_worker_count()
                    
                    # Report worker count changes
                    if current_workers != last_worker_count:
                        self.progress.emit(current_count, total_count, 
                                         f"Processed {current_count}/{total_count} images (workers: {current_workers})")
                        last_worker_count = current_workers
                    elif current_count != last_count:
                        self.progress.emit(current_count, total_count, 
                                         f"Processed {current_count}/{total_count} images")
                    
                    last_count = current_count
                    
                    # Check if processing is complete
                    if current_count >= total_count:
                        break
                        
                    time.sleep(0.5)
            
            monitor_thread = threading.Thread(target=monitor_progress)
            monitor_thread.start()
            
            # Process with cancellation support
            success = processor.process_folder_with_cancellation(
                self.input_folder,
                keep_structure=False,
                delay_between_submissions=DELAY_BETWEEN_SUBMISSIONS,
                cancellation_check=lambda: self._cancelled
            )
            
            monitor_thread.join(timeout=2)
            client_pool.close_all()
            self.finished.emit(success)
            
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)


class MultiServerRipWorker(QObject):
    """Worker for multi-server RIP processing with distribution"""
    finished = Signal(bool)
    error = Signal(str)
    progress = Signal(int, int, str)  # processed, total, message
    image_done = Signal(str)  # rip file path
    
    def __init__(self, input_folder: str, output_folder: str, server_configs: list, distribution_mode='alternate'):
        super().__init__()
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.server_configs = server_configs
        self.distribution_mode = distribution_mode
        self._cancelled = False
    
    def cancel(self):
        self._cancelled = True
    
    def run(self):
        try:
            from pages.images_to_rip.images_to_rip import MultiServerClientPool, MultiServerImageRipProcessor
            
            # Configuration
            CONNECTIONS_PER_SERVER = 4  # Connections per server
            MAX_WORKERS = 12  # Total worker threads
            DELAY_BETWEEN_SUBMISSIONS = 0.2
            
            # Initialize multi-server client pool
            multi_pool = MultiServerClientPool(
                server_configs=self.server_configs,
                connections_per_server=CONNECTIONS_PER_SERVER
            )
            
            if not multi_pool.initialize():
                self.error.emit("Failed to connect to one or more servers")
                self.finished.emit(False)
                return
            
            # Create multi-server processor
            processor = MultiServerImageRipProcessor(
                multi_server_pool=multi_pool,
                output_dir=self.output_folder,
                max_workers=MAX_WORKERS,
                distribution_mode=self.distribution_mode
            )
            
            # Pass cancellation flag
            processor.set_cancellation_callback(lambda: self._cancelled)
            
            # Get total count
            from pathlib import Path
            folder_path = Path(self.input_folder)
            image_files = []
            SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif'}
            for file_path in folder_path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    image_files.append(file_path)
            total_count = len(image_files)
            
            # Monitor progress
            import threading
            def monitor_progress():
                last_count = 0
                
                while not self._cancelled:
                    if self._cancelled:
                        processor.cancel_processing()
                        break
                    
                    current_count = processor.processed_count
                    
                    if current_count != last_count:
                        server_count = multi_pool.get_server_count()
                        mode_str = "alternate" if self.distribution_mode == 'alternate' else "chunks"
                        self.progress.emit(
                            current_count, total_count,
                            f"Processed {current_count}/{total_count} images ({server_count} servers, {mode_str})"
                        )
                    
                    last_count = current_count
                    
                    if current_count >= total_count:
                        break
                    
                    time.sleep(0.5)
            
            monitor_thread = threading.Thread(target=monitor_progress)
            monitor_thread.start()
            
            # Process with multi-server distribution
            success = processor.process_folder_with_cancellation(
                self.input_folder,
                keep_structure=False,
                delay_between_submissions=DELAY_BETWEEN_SUBMISSIONS,
                cancellation_check=lambda: self._cancelled
            )
            
            monitor_thread.join(timeout=2)
            multi_pool.close_all()
            self.finished.emit(success)
            
        except Exception as e:
            import traceback
            self.error.emit(f"Multi-server RIP error: {str(e)}\n{traceback.format_exc()}")
            self.finished.emit(False)

    def _switch_section(self, section_index):
        """
        Switches to the specified section and updates button states.
        """
        self.current_section = section_index
        
        # Map buttons to their section indices (section 7 has no button - PAGE IMPOSE)
        button_section_map = {
            0: self.pdf_split_btn,
            1: self.colour_conv_btn,
            2: self.pdf_to_images_btn,
            3: self.images_to_rip_btn,
            4: self.print_rip_btn,
            5: self.consolidated_btn,
            6: self.build_csv_btn,
            8: self.multi_server_btn,  # Section 7 (PAGE IMPOSE) has no button, so multi-server is at index 8
            9: self.server_config_btn   # Server config at index 9
        }
        
        # Update all button states
        for sec_idx, button in button_section_map.items():
            if sec_idx == section_index:
                button.setProperty("active", True)
                button.style().unpolish(button)
                button.style().polish(button)
            else:
                button.setProperty("active", False)
                button.style().unpolish(button)
                button.style().polish(button)
        
        # Switch to the corresponding widget
        self.stacked_widget.setCurrentIndex(section_index)

    def closeEvent(self, event):
        """
        Handles the main window close event.
        """
        reply = QMessageBox.question(self, 'Quit Application',
                                     "Are you sure you want to quit?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                logging.getLogger(__name__).info("Application closing; finalizing logs")
                
                # Stop and cleanup any running threads
                self._cleanup_threads()
                
                if hasattr(self, 'session_logger') and self.session_logger:
                    self.session_logger.close()
            except Exception as e:
                logging.getLogger(__name__).error(f"Error during cleanup: {e}")
            event.accept()
        else:
            event.ignore()
    
    def _cleanup_threads(self):
        """
        Cleanup all running threads gracefully
        """
        threads_to_cleanup = []
        
        # Check for print thread
        if hasattr(self, 'print_thread') and self.print_thread and self.print_thread.isRunning():
            threads_to_cleanup.append(('print_thread', self.print_thread, getattr(self, 'print_worker', None)))
        
        # Check for conversion thread in PDF render section
        if hasattr(self, 'pdf_render_section'):
            if hasattr(self.pdf_render_section, 'conversion_thread') and \
               self.pdf_render_section.conversion_thread and \
               self.pdf_render_section.conversion_thread.isRunning():
                threads_to_cleanup.append(('conversion_thread', 
                                          self.pdf_render_section.conversion_thread, 
                                          getattr(self.pdf_render_section, 'conversion_worker', None)))
        
        # Check for multi-server threads
        if hasattr(self, 'multi_server_section'):
            if hasattr(self.multi_server_section, 'threads'):
                for server_id, thread in self.multi_server_section.threads.items():
                    if thread and thread.isRunning():
                        worker = self.multi_server_section.workers.get(server_id)
                        threads_to_cleanup.append((f'multi_server_{server_id}', thread, worker))
        
        # Check for page impose thread
        if hasattr(self, 'page_impose_section'):
            if hasattr(self.page_impose_section, 'processing_thread') and \
               self.page_impose_section.processing_thread and \
               self.page_impose_section.processing_thread.isRunning():
                threads_to_cleanup.append(('impose_thread', 
                                          self.page_impose_section.processing_thread, 
                                          None))
        
        # Cleanup each thread
        for name, thread, worker in threads_to_cleanup:
            try:
                logging.getLogger(__name__).info(f"Stopping thread: {name}")
                
                # Request worker to stop if it has stop mechanism
                if worker and hasattr(worker, 'stop'):
                    worker.stop()
                elif worker and hasattr(worker, 'stop_requested'):
                    worker.stop_requested = True
                
                # Wait for thread to finish (with timeout)
                thread.quit()
                if not thread.wait(2000):  # Wait max 2 seconds
                    logging.getLogger(__name__).warning(f"Thread {name} did not stop gracefully, terminating")
                    thread.terminate()
                    thread.wait(1000)  # Wait max 1 second after terminate
                
                logging.getLogger(__name__).info(f"Thread {name} stopped successfully")
            except Exception as e:
                logging.getLogger(__name__).error(f"Error stopping thread {name}: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Show splash screen FIRST before anything else
    splash = show_splash_screen(app)
    
    # Force the splash screen to render immediately
    app.processEvents()
    
    # Apply global font
    try:
        _apply_global_font()
    except Exception:
        pass

    # Present login dialog (full screen, GUI only for now)
    login_dialog = LoginDialog()
    login_dialog.showFullScreen()
    if login_dialog.exec() != QDialog.Accepted:
        sys.exit(0)

    # Once login completes, close splash
    splash.close()
    
    # Process events again to ensure splash is fully rendered
    app.processEvents()
    
    # Create main window (but don't show it yet) - this loads in background
    window = MainApplication()
    
    # Show main window after splash screen fades out (3 seconds total)
    from PySide6.QtCore import QTimer
    QTimer.singleShot(3000, window.show)
    
    sys.exit(app.exec())
