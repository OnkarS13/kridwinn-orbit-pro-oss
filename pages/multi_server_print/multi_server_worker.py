"""
Multi-Server Print Worker - Worker thread for individual printer servers
"""
import logging
from PySide6.QtCore import QObject, Signal
from pages.rip_to_print.rip_to_print import GUIRipPrinter
from .server_config import PrinterServerConfig

logger = logging.getLogger(__name__)


class MultiServerPrintWorker(QObject):
    """Worker object to handle RIP printing for a specific server in a separate thread"""
    
    finished = Signal(str, bool)  # server_id, success
    progress = Signal(str, int, int, str)  # server_id, processed, total, status message
    error = Signal(str, str)  # server_id, error message
    files_discovered = Signal(str, int)  # server_id, number of files
    connection_status = Signal(str, bool, str)  # server_id, connected?, message
    
    def __init__(self, server_id: str, server_config: PrinterServerConfig, page_filter: dict):
        super().__init__()
        self.server_id = server_id
        self.config = server_config
        self.page_filter = page_filter
        self._cancelled = False
        self.gui_printer = None
    
    def cancel(self):
        """Cancel the printing process"""
        self._cancelled = True
        if self.gui_printer:
            self.gui_printer.cancel()
    
    def run(self):
        """Execute the RIP printing with progress updates"""
        try:
            # Create GUI printer with server-specific host and port
            self.gui_printer = GUIRipPrinter(self.config.ip, self.config.port)
            
            # Define progress callback
            def progress_callback(processed, total, message):
                if not self._cancelled:
                    self.progress.emit(self.server_id, processed, total, message)
            
            # Connect to server
            self.connection_status.emit(
                self.server_id,
                False,
                f"Connecting to {self.config.ip}:{self.config.port}..."
            )
            
            if not self.gui_printer.connect():
                self.connection_status.emit(
                    self.server_id,
                    False,
                    f"Failed to connect to {self.config.ip}:{self.config.port}"
                )
                self.error.emit(
                    self.server_id,
                    f"Failed to connect to Print Server at {self.config.ip}:{self.config.port}"
                )
                self.finished.emit(self.server_id, False)
                return
            else:
                self.connection_status.emit(
                    self.server_id,
                    True,
                    f"Connected to {self.config.ip}:{self.config.port}"
                )
            
            # Discover files first to get count
            from pages.rip_to_print.rip_to_print import RIPFolderPrinter
            temp_printer = RIPFolderPrinter(self.gui_printer.client)
            files_with_sizes = temp_printer.discover_rip_files(
                self.config.rip_folder,
                pattern=self.config.pattern,
                recursive=self.config.recursive
            )
            
            if not files_with_sizes:
                self.error.emit(
                    self.server_id,
                    "No RIP files found in the specified folder"
                )
                self.finished.emit(self.server_id, False)
                return
            
            # Apply page filter
            filtered = self._apply_page_filter(files_with_sizes)
            total_files = len(filtered)
            self.files_discovered.emit(self.server_id, total_files)
            
            # Check for cancellation
            if self._cancelled:
                self.progress.emit(self.server_id, 0, total_files, "Printing cancelled by user")
                self.finished.emit(self.server_id, False)
                return
            
            # Print using the module (continuous or normal mode)
            if self.config.continuous_mode:
                success = self.gui_printer.print_rip_folder_continuous_with_callback(
                    self.config.rip_folder,
                    progress_callback,
                    pattern=self.config.pattern,
                    recursive=self.config.recursive,
                    num_copies=self.config.num_copies,
                    max_wait_time=self.config.max_wait_time
                )
            else:
                success = self.gui_printer.print_rip_folder_with_callback(
                    self.config.rip_folder,
                    progress_callback,
                    pattern=self.config.pattern,
                    recursive=self.config.recursive,
                    num_copies=self.config.num_copies,
                    files_override=filtered
                )
            
            if self._cancelled:
                self.progress.emit(self.server_id, 0, total_files, "Printing cancelled by user")
                self.finished.emit(self.server_id, False)
            else:
                self.finished.emit(self.server_id, success)
        
        except Exception as e:
            logger.error(f"Printing failed for server {self.server_id}: {e}")
            self.error.emit(self.server_id, f"Printing failed: {str(e)}")
            self.finished.emit(self.server_id, False)
        finally:
            if self.gui_printer:
                try:
                    self.gui_printer.close()
                except:
                    pass
    
    def _apply_page_filter(self, files_with_sizes):
        """Filter and order files based on page selection rules"""
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
        logger.info(
            f"[Server {self.server_id}] Page selection | "
            f"total={len(files_with_sizes)} | selected={len(filtered)} | "
            f"filter={self.page_filter}"
        )
        
        return filtered

