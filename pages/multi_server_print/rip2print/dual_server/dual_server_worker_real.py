from pathlib import Path
from typing import List, Tuple
from PySide6.QtCore import QObject, Signal
import threading
import logging

logger = logging.getLogger(__name__)


class DualServerWorkerReal(QObject):
    """
    Real dual-server printing worker using two GUIRipPrinter clients.
    Supports:
      - Same folder: odd/even split
      - Separate folders: independent sequences
    Emits per-server progress and overall finished/error signals.
    """

    progress = Signal(str, int, int, str)  # server_tag, processed, total, message
    finished = Signal(bool)
    error = Signal(str)
    status_update = Signal(str, dict)      # server_tag, {sent, printed, total, speed}
    error_occurred = Signal(str, dict)     # server_tag, {error_msg, sent, printed, total}
    server_error_detected = Signal(str, dict)  # server_tag, {error_type, error_msg, last_printed, total, can_resume}

    def __init__(
        self,
        server1_ip: str,
        server1_port: int,
        server2_ip: str,
        server2_port: int,
        same_folder: bool,
        folder1: str,
        folder2: str,
        pattern: str,
        copies: int,
        collate_type: int,
        range_mode_all: bool,
        range_from: int,
        range_to: int,
        reverse_order: bool,
        resume_server1_from: int = 0,
        resume_server2_from: int = 0,
        files1_list: list = None,
        files2_list: list = None,
        batch_size: int = 10,
        repeat_resume_pages: int = 1,
        group_settings1: dict = None,  # Per-group settings for Server 1
        print_order1: list = None,     # Print order for Server 1
        group_settings2: dict = None,  # Per-group settings for Server 2
        print_order2: list = None,     # Print order for Server 2
    ):
        super().__init__()
        self.server1_ip = server1_ip
        self.server1_port = int(server1_port)
        self.server2_ip = server2_ip
        self.server2_port = int(server2_port)
        self.same_folder = bool(same_folder)
        self.folder1 = Path(folder1)
        self.folder2 = Path(folder2)
        self.pattern = pattern
        self.copies = max(1, int(copies))
        self.collate_type = 1 if collate_type != 2 else 2
        self.range_mode_all = bool(range_mode_all)
        self.range_from = int(range_from)
        self.range_to = int(range_to)
        self.reverse_order = bool(reverse_order)
        self.resume_server1_from = max(0, int(resume_server1_from))
        self.resume_server2_from = max(0, int(resume_server2_from))
        self.files1_list = files1_list
        self.files2_list = files2_list
        self.batch_size = max(1, int(batch_size))
        # How many previously printed pages to re-send when resuming
        self.repeat_resume_pages = max(0, int(repeat_resume_pages))

        # Per-group settings (for Separate Folders mode with per-group configuration)
        self.group_settings1 = group_settings1
        self.print_order1 = print_order1
        self.group_settings2 = group_settings2
        self.print_order2 = print_order2

        self._cancelled = False
        self._gui1 = None
        self._gui2 = None
        self._print_thread1 = None
        self._print_thread2 = None
        
        # Live label tracking for each server
        self._server1_last_label = 0
        # Initialize label offsets to resume points - adjusted for F.a fix (re-print last N pages)
        # If resuming from page 5 with repeat_resume_pages=2, we start at page 3
        if self.resume_server1_from > 0 and self.repeat_resume_pages > 0:
            self._server1_label_offset = max(0, self.resume_server1_from - self.repeat_resume_pages)
        else:
            self._server1_label_offset = 0
        self._server2_last_label = 0
        if self.resume_server2_from > 0 and self.repeat_resume_pages > 0:
            self._server2_label_offset = max(0, self.resume_server2_from - self.repeat_resume_pages)
        else:
            self._server2_label_offset = 0
        self._server1_lock = threading.Lock()
        self._server2_lock = threading.Lock()
        self._server1_speed = None
        self._server2_speed = None
        self._server1_last_emitted_label = -1  # Track last emitted label to avoid duplicates
        self._server2_last_emitted_label = -1  # Track last emitted label to avoid duplicates

        # Track printed counts for resume state
        self._server1_printed = 0
        self._server2_printed = 0
        self._server1_total = 0
        self._server2_total = 0

        # Track per-group mode for each server (set in run() method)
        self._server1_uses_per_group = False
        self._server2_uses_per_group = False

        # Error detection tracking (per server)
        self._server1_last_traffic_code = None
        self._server1_last_status_code = None
        self._server2_last_traffic_code = None
        self._server2_last_status_code = None
        self._error_detected = False

        # Resume state tracking
        self.resume_state = None  # Will store state when stopped

    def _save_resume_state(self, reason="manual"):
        """Save resume state for both servers"""
        self.resume_state = {
            'server1_last_printed': self._server1_printed,
            'server1_total': self._server1_total,
            'server2_last_printed': self._server2_printed,
            'server2_total': self._server2_total,
            'server1_ip': self.server1_ip,
            'server1_port': self.server1_port,
            'server2_ip': self.server2_ip,
            'server2_port': self.server2_port,
            'same_folder': self.same_folder,
            'folder1': str(self.folder1),
            'folder2': str(self.folder2),
            'pattern': self.pattern,
            'copies': self.copies,
            'collate_type': self.collate_type,
            'range_mode_all': self.range_mode_all,
            'range_from': self.range_from,
            'range_to': self.range_to,
            'reverse_order': self.reverse_order,
            'batch_size': self.batch_size,
            'files1_list': [str(f) for f in self.files1_list] if self.files1_list else None,
            'files2_list': [str(f) for f in self.files2_list] if self.files2_list else None,
            # Per-group settings for resume
            'group_settings1': self.group_settings1,
            'print_order1': self.print_order1,
            'group_settings2': self.group_settings2,
            'print_order2': self.print_order2,
        }
        logger.info(f"Resume state saved ({reason}): Server1={self._server1_printed}/{self._server1_total}, Server2={self._server2_printed}/{self._server2_total}")

    def cancel(self):
        """Cancel printing and abort both servers"""
        self._cancelled = True

        # Save resume state when stopping
        self._save_resume_state(reason="manual_cancel")
        
        # best-effort abort and close on both servers
        try:
            if self._gui1 and getattr(self._gui1, 'client', None):
                try:
                    # Cancel the printer instance if it exists
                    if hasattr(self._gui1, 'printer') and self._gui1.printer:
                        self._gui1.printer.cancel()
                    # Send abort command
                    if hasattr(self._gui1.client, 'abort_print'):
                        self._gui1.client.abort_print()
                    # Close the connection to interrupt operations
                    self._gui1.close()
                    self._gui1 = None
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if self._gui2 and getattr(self._gui2, 'client', None):
                try:
                    # Cancel the printer instance if it exists
                    if hasattr(self._gui2, 'printer') and self._gui2.printer:
                        self._gui2.printer.cancel()
                    # Send abort command
                    if hasattr(self._gui2.client, 'abort_print'):
                        self._gui2.client.abort_print()
                    # Close the connection to interrupt operations
                    self._gui2.close()
                    self._gui2 = None
                except Exception:
                    pass
        except Exception:
            pass

    def _handle_server_error(self, server_tag: str, error_type: str, error_msg: str):
        """Handle server errors with auto-save and notification"""
        if self._error_detected:
            return  # Already handling an error

        self._error_detected = True

        # Save resume state automatically
        self._save_resume_state(reason=f"server_error_{server_tag}_{error_type}")

        # Determine which server's counts to use
        if server_tag == "server1":
            last_printed = self._server1_printed
            total = self._server1_total
            resume_from = max(0, last_printed - self.repeat_resume_pages) if self.repeat_resume_pages > 0 else last_printed
        elif server_tag == "server2":
            last_printed = self._server2_printed
            total = self._server2_total
            resume_from = max(0, last_printed - self.repeat_resume_pages) if self.repeat_resume_pages > 0 else last_printed
        else:  # "both"
            last_printed = self._server1_printed + self._server2_printed
            total = self._server1_total + self._server2_total
            resume_from = max(0, last_printed - self.repeat_resume_pages) if self.repeat_resume_pages > 0 else last_printed

        # Emit detailed error signal for UI
        error_details = {
            'error_type': error_type,
            'error_msg': error_msg,
            'last_printed': last_printed,
            'total': total,
            'can_resume': True,
            'resume_from': resume_from
        }

        logger.error(f"Server error detected on {server_tag}: {error_type} - {error_msg} at page {last_printed}/{total}")

        # Emit both signals for compatibility
        self.error_occurred.emit(server_tag, {
            'error_msg': f"Server Error ({error_type}): {error_msg}",
            'sent': 0,
            'printed': last_printed,
            'total': total
        })
        self.server_error_detected.emit(server_tag, error_details)

        # Mark as cancelled to stop further processing
        self._cancelled = True

    def run(self):
        from pages.rip_to_print.rip_to_print import GUIRipPrinter, RIPFolderPrinter

        try:
            if self.same_folder:
                if not self.folder1.is_dir():
                    error_msg = "Folder not found"
                    self.error.emit(error_msg)
                    self.error_occurred.emit("both", {
                        'error_msg': error_msg,
                        'sent': 0,
                        'printed': 0,
                        'total': 0
                    })
                    self.finished.emit(False)
                    return
                # Discover once
                # Use a temporary client (localhost defaults are fine for discovery)
                temp_client = GUIRipPrinter(self.server1_ip, self.server1_port)
                if not temp_client.connect():
                    error_msg = f"Failed to connect to {self.server1_ip}:{self.server1_port}"
                    self.error.emit(error_msg)
                    self.error_occurred.emit("server1", {
                        'error_msg': error_msg,
                        'sent': 0,
                        'printed': 0,
                        'total': 0
                    })
                    self.finished.emit(False)
                    return
                if self.files1_list is not None:
                    # Use pre-filtered files from file grouping
                    files_with_sizes = []
                    for f_path in self.files1_list:
                        p = Path(f_path)
                        try:
                            s = p.stat().st_size
                        except Exception:
                            s = 0
                        files_with_sizes.append((p, s))
                else:
                    # Discover all files
                    rip = RIPFolderPrinter(temp_client.client)
                    files_with_sizes: List[Tuple[Path, int]] = rip.discover_rip_files(
                        str(self.folder1), pattern=self.pattern, recursive=False
                    )
                try:
                    temp_client.close()
                except Exception:
                    pass
                # Build size map
                size_map = {p: s for (p, s) in files_with_sizes}
                files = [p for (p, _s) in files_with_sizes]

                # Apply reverse order and page range to ALL files (regardless of source)
                if self.reverse_order:
                    files = list(reversed(files))
                files = self._apply_page_range(files)
                odd, even = self._split_odd_even(files)
                # Emit clarifying messages about actual file counts before copies
                if self.copies > 1:
                    self.progress.emit("server1", 0, 0, f"Processing {len(odd)} unique files × {self.copies} copies = {len(odd) * self.copies} total prints")
                    self.progress.emit("server2", 0, 0, f"Processing {len(even)} unique files × {self.copies} copies = {len(even) * self.copies} total prints")

                # Handle resume with copies logic (F.a + F.d) for Server1
                start_file_index1 = 0
                start_copy_index1 = 0
                if self.resume_server1_from > 0 and self.copies > 1:
                    back_count1 = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
                    resume_index1 = max(0, self.resume_server1_from - back_count1)
                    num_files1 = len(odd)
                    if self.collate_type == 1:
                        start_file_index1 = resume_index1 // self.copies
                        start_copy_index1 = resume_index1 % self.copies
                        logger.info(f"Server1 resuming from File {start_file_index1 + 1}, Copy {start_copy_index1 + 1} (Collate Type 1)")
                    else:
                        start_copy_index1 = resume_index1 // num_files1
                        start_file_index1 = resume_index1 % num_files1
                        logger.info(f"Server1 resuming from Copy {start_copy_index1 + 1}, File {start_file_index1 + 1} (Collate Type 2)")
                    seq1 = self._build_sequence(odd, start_file_index1, start_copy_index1)
                    self._server1_total = num_files1 * self.copies
                    self._server1_printed = resume_index1
                elif self.resume_server1_from > 0:
                    back_count1 = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
                    resume_index1 = max(0, self.resume_server1_from - back_count1)
                    seq1 = self._build_sequence(odd)
                    self._server1_total = len(seq1)
                    if resume_index1 >= len(seq1):
                        logger.info(f"Server1 resume from {self.resume_server1_from} >= total {len(seq1)}, already complete")
                        seq1 = []
                    else:
                        if self.repeat_resume_pages > 0:
                            logger.info(
                                f"Server1 resuming from page {resume_index1 + 1}/{self._server1_total} "
                                f"(re-printing last {self.repeat_resume_pages} page(s))"
                            )
                        else:
                            logger.info(
                                f"Server1 resuming from page {resume_index1 + 1}/{self._server1_total} "
                                "(no re-print on resume)"
                            )
                        seq1 = seq1[resume_index1:]
                        self._server1_printed = resume_index1
                else:
                    seq1 = self._build_sequence(odd)
                    self._server1_total = len(seq1)

                # Handle resume with copies logic (F.a + F.d) for Server2
                start_file_index2 = 0
                start_copy_index2 = 0
                if self.resume_server2_from > 0 and self.copies > 1:
                    back_count2 = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
                    resume_index2 = max(0, self.resume_server2_from - back_count2)
                    num_files2 = len(even)
                    if self.collate_type == 1:
                        start_file_index2 = resume_index2 // self.copies
                        start_copy_index2 = resume_index2 % self.copies
                        logger.info(f"Server2 resuming from File {start_file_index2 + 1}, Copy {start_copy_index2 + 1} (Collate Type 1)")
                    else:
                        start_copy_index2 = resume_index2 // num_files2
                        start_file_index2 = resume_index2 % num_files2
                        logger.info(f"Server2 resuming from Copy {start_copy_index2 + 1}, File {start_file_index2 + 1} (Collate Type 2)")
                    seq2 = self._build_sequence(even, start_file_index2, start_copy_index2)
                    self._server2_total = num_files2 * self.copies
                    self._server2_printed = resume_index2
                elif self.resume_server2_from > 0:
                    back_count2 = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
                    resume_index2 = max(0, self.resume_server2_from - back_count2)
                    seq2 = self._build_sequence(even)
                    self._server2_total = len(seq2)
                    if resume_index2 >= len(seq2):
                        logger.info(f"Server2 resume from {self.resume_server2_from} >= total {len(seq2)}, already complete")
                        seq2 = []
                    else:
                        if self.repeat_resume_pages > 0:
                            logger.info(
                                f"Server2 resuming from page {resume_index2 + 1}/{self._server2_total} "
                                f"(re-printing last {self.repeat_resume_pages} page(s))"
                            )
                        else:
                            logger.info(
                                f"Server2 resuming from page {resume_index2 + 1}/{self._server2_total} "
                                "(no re-print on resume)"
                            )
                        seq2 = seq2[resume_index2:]
                        self._server2_printed = resume_index2
                else:
                    seq2 = self._build_sequence(even)
                    self._server2_total = len(seq2)

                # Store size map for later conversion
                self._size_map = size_map
            else:
                # Discover separately for both folders
                # Get base file lists first (without building full sequences yet)
                files1, size_map1 = self._discover_files(self.server1_ip, self.server1_port, self.folder1, self.files1_list)
                files2, size_map2 = self._discover_files(self.server2_ip, self.server2_port, self.folder2, self.files2_list)

                # Store separate size maps for each server (for per-group mode)
                self._size_map1 = size_map1
                self._size_map2 = size_map2
                # Also merge for backward compatibility with normal mode
                self._size_map = {**size_map1, **size_map2}

                # Check per-group mode for Server 1
                if self.group_settings1 and self.print_order1:
                    seq1 = None  # Will be built inside _process_groups_for_server
                    self._server1_uses_per_group = True
                    logger.info(f"Server1: Per-group mode enabled with {len(self.print_order1)} groups")
                else:
                    self._server1_uses_per_group = False
                    # Emit clarifying message about actual file counts before copies
                    if self.copies > 1:
                        self.progress.emit("server1", 0, 0, f"Processing {len(files1)} unique files × {self.copies} copies = {len(files1) * self.copies} total prints")

                # Check per-group mode for Server 2
                if self.group_settings2 and self.print_order2:
                    seq2 = None  # Will be built inside _process_groups_for_server
                    self._server2_uses_per_group = True
                    logger.info(f"Server2: Per-group mode enabled with {len(self.print_order2)} groups")
                else:
                    self._server2_uses_per_group = False
                    # Emit clarifying message about actual file counts before copies
                    if self.copies > 1:
                        self.progress.emit("server2", 0, 0, f"Processing {len(files2)} unique files × {self.copies} copies = {len(files2) * self.copies} total prints")

                # Handle resume with copies logic (F.a + F.d) for Server1
                # (Only if NOT using per-group mode)
                if not self._server1_uses_per_group:
                    start_file_index1 = 0
                    start_copy_index1 = 0
                    if self.resume_server1_from > 0 and self.copies > 1:
                        back_count1 = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
                        resume_index1 = max(0, self.resume_server1_from - back_count1)
                        num_files1 = len(files1)
                        if self.collate_type == 1:
                            start_file_index1 = resume_index1 // self.copies
                            start_copy_index1 = resume_index1 % self.copies
                            logger.info(f"Server1 resuming from File {start_file_index1 + 1}, Copy {start_copy_index1 + 1} (Collate Type 1)")
                        else:
                            start_copy_index1 = resume_index1 // num_files1
                            start_file_index1 = resume_index1 % num_files1
                            logger.info(f"Server1 resuming from Copy {start_copy_index1 + 1}, File {start_file_index1 + 1} (Collate Type 2)")
                        seq1 = self._build_sequence(files1, start_file_index1, start_copy_index1)
                        self._server1_total = num_files1 * self.copies
                        self._server1_printed = resume_index1
                    elif self.resume_server1_from > 0:
                        back_count1 = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
                        resume_index1 = max(0, self.resume_server1_from - back_count1)
                        seq1 = self._build_sequence(files1)
                        self._server1_total = len(seq1)
                        if resume_index1 >= len(seq1):
                            logger.info(f"Server1 resume from {self.resume_server1_from} >= total {len(seq1)}, already complete")
                            seq1 = []
                        else:
                            if self.repeat_resume_pages > 0:
                                logger.info(
                                    f"Server1 resuming from page {resume_index1 + 1}/{self._server1_total} "
                                    f"(re-printing last {self.repeat_resume_pages} page(s))"
                                )
                            else:
                                logger.info(
                                    f"Server1 resuming from page {resume_index1 + 1}/{self._server1_total} "
                                    "(no re-print on resume)"
                                )
                            seq1 = seq1[resume_index1:]
                            self._server1_printed = resume_index1
                    else:
                        seq1 = self._build_sequence(files1)
                        self._server1_total = len(seq1)

                # Handle resume with copies logic (F.a + F.d) for Server2
                # (Only if NOT using per-group mode)
                if not self._server2_uses_per_group:
                    start_file_index2 = 0
                    start_copy_index2 = 0
                    if self.resume_server2_from > 0 and self.copies > 1:
                        back_count2 = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
                        resume_index2 = max(0, self.resume_server2_from - back_count2)
                        num_files2 = len(files2)
                        if self.collate_type == 1:
                            start_file_index2 = resume_index2 // self.copies
                            start_copy_index2 = resume_index2 % self.copies
                            logger.info(f"Server2 resuming from File {start_file_index2 + 1}, Copy {start_copy_index2 + 1} (Collate Type 1)")
                        else:
                            start_copy_index2 = resume_index2 // num_files2
                            start_file_index2 = resume_index2 % num_files2
                            logger.info(f"Server2 resuming from Copy {start_copy_index2 + 1}, File {start_file_index2 + 1} (Collate Type 2)")
                        seq2 = self._build_sequence(files2, start_file_index2, start_copy_index2)
                        self._server2_total = num_files2 * self.copies
                        self._server2_printed = resume_index2
                    elif self.resume_server2_from > 0:
                        back_count2 = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
                        resume_index2 = max(0, self.resume_server2_from - back_count2)
                        seq2 = self._build_sequence(files2)
                        self._server2_total = len(seq2)
                        if resume_index2 >= len(seq2):
                            logger.info(f"Server2 resume from {self.resume_server2_from} >= total {len(seq2)}, already complete")
                            seq2 = []
                        else:
                            if self.repeat_resume_pages > 0:
                                logger.info(
                                    f"Server2 resuming from page {resume_index2 + 1}/{self._server2_total} "
                                    f"(re-printing last {self.repeat_resume_pages} page(s))"
                                )
                            else:
                                logger.info(
                                    f"Server2 resuming from page {resume_index2 + 1}/{self._server2_total} "
                                    "(no re-print on resume)"
                                )
                            seq2 = seq2[resume_index2:]
                            self._server2_printed = resume_index2
                    else:
                        seq2 = self._build_sequence(files2)
                        self._server2_total = len(seq2)

            # Check for cancellation before starting
            if self._cancelled:
                self.finished.emit(False)
                return
            
            # Print on BOTH servers in PARALLEL using threads
            logger.info("=" * 60)
            logger.info("STARTING PARALLEL DUAL-SERVER PRINTING")
            logger.info("=" * 60)
            # Handle per-group mode where seq1/seq2 might be None
            seq1_info = "per-group mode" if seq1 is None else f"{len(seq1)} files"
            seq2_info = "per-group mode" if seq2 is None else f"{len(seq2)} files"
            logger.info(f"Server 1: {self.server1_ip}:{self.server1_port} - {seq1_info}")
            logger.info(f"Server 2: {self.server2_ip}:{self.server2_port} - {seq2_info}")
            logger.info("Both servers will print SIMULTANEOUSLY")
            logger.info("=" * 60)
            
            results = {'ok1': False, 'ok2': False}
            
            def print_server1():
                logger.info("🟢 Server 1 thread started - beginning print operations")
                results['ok1'] = self._print_sequence(
                    tag="server1",
                    ip=self.server1_ip,
                    port=self.server1_port,
                    folder=str(self.folder1),
                    sequence=seq1,
                )
                logger.info(f"✅ Server 1 thread completed - success: {results['ok1']}")
            
            def print_server2():
                logger.info("🟢 Server 2 thread started - beginning print operations")
                results['ok2'] = self._print_sequence(
                    tag="server2",
                    ip=self.server2_ip,
                    port=self.server2_port,
                    folder=str(self.folder2 if not self.same_folder else self.folder1),
                    sequence=seq2,
                )
                logger.info(f"✅ Server 2 thread completed - success: {results['ok2']}")
            
            # Start both threads simultaneously
            # Set daemon=False to ensure proper cleanup (we manage cleanup ourselves)
            thread1 = threading.Thread(target=print_server1, name="PrintServer1", daemon=False)
            thread2 = threading.Thread(target=print_server2, name="PrintServer2", daemon=False)
            
            # Store thread references for potential cancellation
            self._print_thread1 = thread1
            self._print_thread2 = thread2
            
            logger.info("🚀 Starting both print threads in parallel...")
            thread1.start()
            thread2.start()
            logger.info("⏳ Both threads running - waiting for completion...")
            
            # Wait for both threads to complete with timeout and cancellation checks
            logger.info("⏰ Waiting for Server 1 thread to finish...")
            while thread1.is_alive():
                thread1.join(timeout=0.5)  # Check every 0.5 seconds
                if self._cancelled:
                    logger.info("⚠️ Cancellation detected while waiting for Server 1")
                    break
            logger.info("✓ Server 1 thread finished")
            
            logger.info("⏰ Waiting for Server 2 thread to finish...")
            while thread2.is_alive():
                thread2.join(timeout=0.5)  # Check every 0.5 seconds
                if self._cancelled:
                    logger.info("⚠️ Cancellation detected while waiting for Server 2")
                    break
            logger.info("✓ Server 2 thread finished")
            
            # Verify threads are dead (or cancelled)
            if thread1.is_alive():
                logger.warning("❌ Server 1 thread is still alive after join (may be due to cancellation)")
            if thread2.is_alive():
                logger.warning("❌ Server 2 thread is still alive after join (may be due to cancellation)")
            
            # Small delay to ensure thread resources are fully released
            import time
            time.sleep(0.1)
            
            logger.info("=" * 60)
            logger.info("PARALLEL PRINTING COMPLETED")
            logger.info(f"Server 1 result: {'SUCCESS' if results['ok1'] else 'FAILED'}")
            logger.info(f"Server 2 result: {'SUCCESS' if results['ok2'] else 'FAILED'}")
            logger.info("=" * 60)
            
            # Clear thread references
            self._print_thread1 = None
            self._print_thread2 = None
            
            # Check if cancelled during printing
            if self._cancelled:
                self.finished.emit(False)
                return

            self.finished.emit(bool(results['ok1'] and results['ok2']))
        except Exception as e:
            error_msg = str(e)

            # Determine error type and handle appropriately
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                error_type = "TIMEOUT_ERROR"
                detailed_msg = f"Print operation timed out after 600s: {error_msg}"
            elif "failed to queue" in error_msg.lower():
                error_type = "QUEUE_ERROR"
                detailed_msg = f"Failed to queue files: {error_msg}"
            elif "underrun" in error_msg.lower():
                error_type = "UNDERRUN_ERROR"
                detailed_msg = f"Buffer underrun detected: {error_msg}"
            else:
                error_type = "GENERAL_ERROR"
                detailed_msg = error_msg

            # Auto-save resume state on error
            if not self._error_detected:
                self._handle_server_error("both", error_type, detailed_msg)

            # Emit legacy error signal for compatibility
            self.error.emit(error_msg)

            self.finished.emit(False)

    def _discover_files(self, ip: str, port: int, folder: Path, files_list: list = None):
        """
        Discover files and return file list with size map (without building sequence).
        Used for separate folders mode with resume support.
        """
        from pages.rip_to_print.rip_to_print import GUIRipPrinter, RIPFolderPrinter

        if files_list is not None:
            # Use pre-filtered files from file grouping
            files_with_sizes = []
            for f_path in files_list:
                p = Path(f_path)
                try:
                    s = p.stat().st_size
                except Exception:
                    s = 0
                files_with_sizes.append((p, s))
        else:
            # Normal discovery
            if not folder.is_dir():
                return [], {}
            cli = GUIRipPrinter(ip, port)
            if not cli.connect():
                return [], {}
            rip = RIPFolderPrinter(cli.client)
            files_with_sizes: List[Tuple[Path, int]] = rip.discover_rip_files(
                str(folder), pattern=self.pattern, recursive=False
            )
            try:
                cli.close()
            except Exception:
                pass

        # Build size map
        size_map = {p: s for (p, s) in files_with_sizes}
        files = [p for (p, _s) in files_with_sizes]

        # Apply reverse order and page range to ALL files (regardless of source)
        if self.reverse_order:
            files = list(reversed(files))
        files = self._apply_page_range(files)
        return files, size_map

    def _discover_and_build(self, ip: str, port: int, folder: Path, files_list: list = None):
        from pages.rip_to_print.rip_to_print import GUIRipPrinter, RIPFolderPrinter

        if files_list is not None:
            # Use pre-filtered files from file grouping
            files_with_sizes = []
            for f_path in files_list:
                p = Path(f_path)
                try:
                    s = p.stat().st_size
                except Exception:
                    s = 0
                files_with_sizes.append((p, s))
        else:
            # Normal discovery
            if not folder.is_dir():
                return [], {}
            cli = GUIRipPrinter(ip, port)
            if not cli.connect():
                return [], {}
            rip = RIPFolderPrinter(cli.client)
            files_with_sizes: List[Tuple[Path, int]] = rip.discover_rip_files(
                str(folder), pattern=self.pattern, recursive=False
            )
            try:
                cli.close()
            except Exception:
                pass

        # Build size map
        size_map = {p: s for (p, s) in files_with_sizes}
        files = [p for (p, _s) in files_with_sizes]

        # Apply reverse order and page range to ALL files (regardless of source)
        if self.reverse_order:
            files = list(reversed(files))
        files = self._apply_page_range(files)
        return self._build_sequence(files), size_map

    def _handle_status_event_server1(self, event):
        """Handle status events for server 1"""
        if event.get('category') != 'print':
            return

        evt = event.get('event')

        # ERROR DETECTION: Traffic light code 3 indicates error
        if evt == 'traffic':
            traffic_code = event.get('code')
            self._server1_last_traffic_code = traffic_code
            if traffic_code == 3:  # Error state
                self._handle_server_error(
                    server_tag="server1",
                    error_type="TRAFFIC_LIGHT_ERROR",
                    error_msg="Server 1 reported traffic light error (code 3)"
                )
                return

        # ERROR DETECTION: Status error codes
        elif evt == 'status':
            status_code = event.get('code')
            status_text = event.get('text', '')
            self._server1_last_status_code = status_code

            # Error codes from GIS documentation
            ERROR_STATUS_CODES = {
                4: "Init PMB Error",
                9: "Transport Failed",
                19: "Security Failed"
            }

            if status_code in ERROR_STATUS_CODES:
                self._handle_server_error(
                    server_tag="server1",
                    error_type=f"STATUS_ERROR_{status_code}",
                    error_msg=f"Server 1 {ERROR_STATUS_CODES[status_code]}: {status_text}"
                )
                return

        # NORMAL EVENTS: Label printing
        elif evt == 'label':
            label_num = event.get('label', 0)
            with self._server1_lock:
                # Detect printer restart (label count goes backwards)
                # But don't double-count the resume_server1_from offset
                if label_num < self._server1_last_label and self._server1_last_label > 0:
                    # Label counter restarted - add previous max to offset
                    self._server1_label_offset += self._server1_last_label
                self._server1_last_label = label_num
                # Calculate real printed count and emit progress message
                real_printed = self._server1_last_label + self._server1_label_offset
                self._server1_printed = max(self._server1_printed, real_printed)
            # Emit progress message only if label changed (deduplicate)
            if real_printed != self._server1_last_emitted_label:
                self._server1_last_emitted_label = real_printed
                self.progress.emit("server1", real_printed, self._server1_total, f"Printed label {real_printed}")

            # Safety check: If we've printed all expected pages, log completion
            if self._server1_total > 0 and self._server1_printed >= self._server1_total:
                logger.info(f"Safety check Server1: Reached completion ({self._server1_printed}/{self._server1_total}) - all copies printed")

        elif evt == 'end_print':
            # End of printing - finalize the count
            with self._server1_lock:
                self._server1_last_label = max(self._server1_last_label, 0)
            # Safety check: Log end_print event received
            if self._server1_total > 0:
                logger.info(f"Safety check Server1: Received end_print event ({self._server1_printed}/{self._server1_total})")

        elif evt == 'speed':
            speed_val = event.get('speed_mpm')
            try:
                self._server1_speed = float(speed_val) if speed_val is not None else None
            except (TypeError, ValueError):
                pass
    
    def _handle_status_event_server2(self, event):
        """Handle status events for server 2"""
        if event.get('category') != 'print':
            return

        evt = event.get('event')

        # ERROR DETECTION: Traffic light code 3 indicates error
        if evt == 'traffic':
            traffic_code = event.get('code')
            self._server2_last_traffic_code = traffic_code
            if traffic_code == 3:  # Error state
                self._handle_server_error(
                    server_tag="server2",
                    error_type="TRAFFIC_LIGHT_ERROR",
                    error_msg="Server 2 reported traffic light error (code 3)"
                )
                return

        # ERROR DETECTION: Status error codes
        elif evt == 'status':
            status_code = event.get('code')
            status_text = event.get('text', '')
            self._server2_last_status_code = status_code

            # Error codes from GIS documentation
            ERROR_STATUS_CODES = {
                4: "Init PMB Error",
                9: "Transport Failed",
                19: "Security Failed"
            }

            if status_code in ERROR_STATUS_CODES:
                self._handle_server_error(
                    server_tag="server2",
                    error_type=f"STATUS_ERROR_{status_code}",
                    error_msg=f"Server 2 {ERROR_STATUS_CODES[status_code]}: {status_text}"
                )
                return

        # NORMAL EVENTS: Label printing
        elif evt == 'label':
            label_num = event.get('label', 0)
            with self._server2_lock:
                # Detect printer restart (label count goes backwards)
                # But don't double-count the resume_server2_from offset
                if label_num < self._server2_last_label and self._server2_last_label > 0:
                    # Label counter restarted - add previous max to offset
                    self._server2_label_offset += self._server2_last_label
                self._server2_last_label = label_num
                # Calculate real printed count and emit progress message
                real_printed = self._server2_last_label + self._server2_label_offset
                self._server2_printed = max(self._server2_printed, real_printed)
            # Emit progress message only if label changed (deduplicate)
            if real_printed != self._server2_last_emitted_label:
                self._server2_last_emitted_label = real_printed
                self.progress.emit("server2", real_printed, self._server2_total, f"Printed label {real_printed}")

            # Safety check: If we've printed all expected pages, log completion
            if self._server2_total > 0 and self._server2_printed >= self._server2_total:
                logger.info(f"Safety check Server2: Reached completion ({self._server2_printed}/{self._server2_total}) - all copies printed")

        elif evt == 'end_print':
            # End of printing - finalize the count
            with self._server2_lock:
                self._server2_last_label = max(self._server2_last_label, 0)
            # Safety check: Log end_print event received
            if self._server2_total > 0:
                logger.info(f"Safety check Server2: Received end_print event ({self._server2_printed}/{self._server2_total})")

        elif evt == 'speed':
            speed_val = event.get('speed_mpm')
            try:
                self._server2_speed = float(speed_val) if speed_val is not None else None
            except (TypeError, ValueError):
                pass

    def _print_sequence(self, tag: str, ip: str, port: int, folder: str, sequence: List[Path]) -> bool:
        from pages.rip_to_print.rip_to_print import GUIRipPrinter
        
        # Get the original total for this server
        original_total = self._server1_total if tag == "server1" else self._server2_total

        # Check for empty sequence (but not None, which is used for per-group mode)
        if sequence is not None and not sequence:
            # Nothing to print (already complete or empty) - report with original total
            resume_from = self.resume_server1_from if tag == "server1" else self.resume_server2_from
            self.status_update.emit(tag, {'sent': resume_from, 'printed': resume_from, 'total': original_total})
            return True
        # Check for cancellation before connecting
        if self._cancelled:
            return False
        gui = GUIRipPrinter(ip, port)
        if not gui.connect():
            error_msg = f"Failed to connect to {ip}:{port}"
            self.error.emit(error_msg)
            self.error_occurred.emit(tag, {
                'error_msg': error_msg,
                'sent': 0,
                'printed': 0,
                'total': original_total
            })
            return False
        # hold refs for abort
        if tag == "server1":
            self._gui1 = gui
        else:
            self._gui2 = gui
        
        # Register status listener for live label tracking
        try:
            if tag == "server1":
                gui.client.add_status_listener(self._handle_status_event_server1)
            else:
                gui.client.add_status_listener(self._handle_status_event_server2)
        except Exception as status_err:
            logger.debug(f"Unable to register status listener for {tag}: {status_err}")
        
        # Use the ORIGINAL total (before any resume slicing) for accurate progress tracking
        total = self._server1_total if tag == "server1" else self._server2_total
        
        # Track actual progress
        actual_sent = [0]  # Use list to allow modification in nested function
        actual_printed = [0]
        
        # Set initial printed count if resuming
        if tag == "server1" and self.resume_server1_from > 0:
            actual_printed[0] = self.resume_server1_from
        elif tag == "server2" and self.resume_server2_from > 0:
            actual_printed[0] = self.resume_server2_from
        
        # Start a background thread to periodically emit status updates based on live label events
        status_thread_stop = threading.Event()
        
        def _status_updater():
            """Periodically emit status updates even when callback isn't being called"""
            import time
            last_emitted_label = [0]  # Track last label we showed in progress
            last_speed = [None]
            while not status_thread_stop.is_set() and not self._cancelled:
                time.sleep(0.2)  # Check every 200ms for smoother updates
                # Get real printed count
                if tag == "server1":
                    with self._server1_lock:
                        real_printed = self._server1_last_label + self._server1_label_offset
                        current_label = self._server1_last_label
                        speed_val = self._server1_speed
                else:
                    with self._server2_lock:
                        real_printed = self._server2_last_label + self._server2_label_offset
                        current_label = self._server2_last_label
                        speed_val = self._server2_speed
                
                
                # Update printed count if it changed
                emit_status = False
                if real_printed > actual_printed[0]:
                    actual_printed[0] = min(total, max(actual_printed[0], real_printed))
                    # Don't emit "Printed label" here - it's already emitted in status event handler
                    emit_status = True


                if speed_val is not None:
                    try:
                        speed_val = float(speed_val)
                    except (TypeError, ValueError):
                        speed_val = None
                if speed_val is not None and (last_speed[0] is None or abs(last_speed[0] - speed_val) > 0.05):
                    last_speed[0] = speed_val
                    emit_status = True

                if emit_status:
                    payload = {
                        'sent': actual_sent[0],
                        'printed': actual_printed[0],
                        'total': total
                    }
                    if speed_val is not None:
                        payload['speed'] = speed_val
                    self.status_update.emit(tag, payload)
        
        status_thread = threading.Thread(target=_status_updater, daemon=True, name=f"StatusUpdater-{tag}")
        status_thread.start()

        def _cb(processed: int, _total: int, message: str):
            # The 'processed' parameter is actually a percentage (0-100) in many cases
            # Parse the actual counts from the message or use percentage to calculate
            estimated_sent = actual_sent[0]
            try:
                # Try to extract actual counts from message like "Queued 50/100 files"
                import re
                match = re.search(r'Queued\s+(\d+)/(\d+)', message)
                if match:
                    estimated_sent = int(match.group(1))
                elif "completed" in message.lower() or "finished" in message.lower():
                    # Completion message - set to total
                    estimated_sent = total
                else:
                    # Use percentage to calculate
                    if processed <= 100:  # It's a percentage
                        sent = int((processed / 100.0) * total)
                        estimated_sent = max(estimated_sent, sent)  # Don't go backwards
                    else:  # It's an actual count
                        estimated_sent = min(processed, total)  # Cap at total
            except Exception:
                # Fallback: treat as percentage if <= 100, otherwise as count
                if processed <= 100:
                    sent = int((processed / 100.0) * total)
                    estimated_sent = max(estimated_sent, sent)
                else:
                    estimated_sent = min(processed, total)
            
            # Update sent count
            actual_sent[0] = min(total, max(actual_sent[0], estimated_sent))
            
            # For printed count, use the real label events from the status listener
            if tag == "server1":
                with self._server1_lock:
                    real_printed = self._server1_last_label + self._server1_label_offset
            else:
                with self._server2_lock:
                    real_printed = self._server2_last_label + self._server2_label_offset
            
            # Ensure printed count reflects real progress (not limited by sent count)
            actual_printed[0] = min(total, max(actual_printed[0], real_printed))
            
            # Update class-level printed counters for resume state
            if tag == "server1":
                self._server1_printed = max(self._server1_printed, actual_printed[0])
            else:
                self._server2_printed = max(self._server2_printed, actual_printed[0])
            
            self.progress.emit(tag, actual_printed[0], total, message)

            speed_val = self._server1_speed if tag == "server1" else self._server2_speed
            payload = {
                'sent': actual_sent[0],
                'printed': actual_printed[0],
                'total': total
            }
            if speed_val is not None:
                try:
                    payload['speed'] = float(speed_val)
                except (TypeError, ValueError):
                    pass
            self.status_update.emit(tag, payload)

        # Check if this server uses per-group mode
        uses_per_group = (tag == "server1" and self._server1_uses_per_group) or \
                         (tag == "server2" and self._server2_uses_per_group)

        if uses_per_group:
            # Per-group processing mode
            group_settings = self.group_settings1 if tag == "server1" else self.group_settings2
            print_order = self.print_order1 if tag == "server1" else self.print_order2
            # Use the correct size map for this server
            server_size_map = self._size_map1 if tag == "server1" else self._size_map2

            try:
                ok = self._process_groups_for_server(
                    tag=tag,
                    gui=gui,
                    group_settings=group_settings,
                    print_order=print_order,
                    folder=folder,
                    _cb=_cb,
                    size_map=server_size_map
                )
            except Exception as e:
                # Error handling will be same as below
                if not self._cancelled:
                    error_msg = str(e)
                    logger.error(f"Per-group print error on {tag}: {error_msg}")

                    # Auto-save resume state on error
                    if not self._error_detected:
                        self._handle_server_error(tag, "GENERAL_ERROR", f"{tag}: {error_msg}")

                    # Emit error
                    server_printed = self._server1_printed if tag == "server1" else self._server2_printed
                    server_total = self._server1_total if tag == "server1" else self._server2_total
                    self.error_occurred.emit(tag, {
                        'error_msg': error_msg,
                        'sent': actual_sent[0],
                        'printed': server_printed,
                        'total': server_total
                    })
                ok = False
        else:
            # Normal sequence processing mode
            # Convert sequence to (path, size) tuples using stored size map
            # Ensure all paths are Path objects (defensive programming for edge cases)
            sequence_with_sizes = [(Path(p) if not isinstance(p, Path) else p, self._size_map.get(p, 0)) for p in sequence]

            try:
                ok = gui.print_rip_folder_with_callback(
                folder,
                _cb,
                pattern=self.pattern,
                recursive=False,
                num_copies=1,  # copies already expanded into sequence
                files_override=sequence_with_sizes,
                batch_size=self.batch_size
                )
            except Exception as e:
                # Handle any errors during printing (including socket errors from cancel)
                if not self._cancelled:
                    error_msg = str(e)
                    logger.error(f"Print error on {tag}: {error_msg}")

                    # Determine error type and handle appropriately
                    if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                        error_type = "TIMEOUT_ERROR"
                        detailed_msg = f"{tag} print operation timed out after 600s: {error_msg}"
                    elif "failed to queue" in error_msg.lower():
                        error_type = "QUEUE_ERROR"
                        detailed_msg = f"{tag} failed to queue files: {error_msg}"
                    elif "underrun" in error_msg.lower():
                        error_type = "UNDERRUN_ERROR"
                        detailed_msg = f"{tag} buffer underrun detected: {error_msg}"
                    else:
                        error_type = "GENERAL_ERROR"
                        detailed_msg = f"{tag}: {error_msg}"

                    # Auto-save resume state on error
                    if not self._error_detected:
                        self._handle_server_error(tag, error_type, detailed_msg)

                    # Emit detailed error with last known counts (for backward compatibility)
                    server_printed = self._server1_printed if tag == "server1" else self._server2_printed
                    server_total = self._server1_total if tag == "server1" else self._server2_total
                    self.error_occurred.emit(tag, {
                        'error_msg': error_msg,
                        'sent': actual_sent[0],
                        'printed': server_printed,
                        'total': server_total
                    })
                ok = False
        
        # Stop the status updater thread
        status_thread_stop.set()
        status_thread.join(timeout=2.0)
        
        # Unregister status listener before closing
        try:
            if tag == "server1":
                gui.client.remove_status_listener(self._handle_status_event_server1)
            else:
                gui.client.remove_status_listener(self._handle_status_event_server2)
        except Exception:
            pass
        
        # Close connection if not already closed by cancel
        if tag == "server1":
            if self._gui1 is not None:
                try:
                    gui.close()
                except Exception:
                    pass
            self._gui1 = None
        else:
            if self._gui2 is not None:
                try:
                    gui.close()
                except Exception:
                    pass
            self._gui2 = None
        
        # Return False if cancelled, otherwise return actual result
        return bool(ok) and not self._cancelled

    def _apply_page_range(self, files: List[Path]) -> List[Path]:
        if self.range_mode_all:
            return files
        lo = max(1, min(self.range_from, self.range_to))
        hi = max(self.range_from, self.range_to)
        return [f for idx, f in enumerate(files, start=1) if lo <= idx <= hi]

    def _split_odd_even(self, files: List[Path]):
        odd = [f for idx, f in enumerate(files, start=1) if idx % 2 == 1]
        even = [f for idx, f in enumerate(files, start=1) if idx % 2 == 0]
        return odd, even

    def _build_sequence(self, files: List[Path], start_file_index: int = 0, start_copy_index: int = 0) -> List[Path]:
        """
        Build print sequence with support for resuming from specific (file_index, copy_index).

        Args:
            files: List of files to print
            start_file_index: Which file to start from (0-based)
            start_copy_index: Which copy to start from (0-based)

        Returns:
            List of files in print order
        """
        if self.collate_type == 1:
            # Collate Type 1: File by File (AAAA BBBB)
            # Print all copies of file A, then all copies of file B
            seq = []
            for file_idx, f in enumerate(files):
                if file_idx < start_file_index:
                    # Skip files before resume point
                    continue
                elif file_idx == start_file_index:
                    # Partial copies for the resume file
                    remaining_copies = self.copies - start_copy_index
                    seq.extend([f] * remaining_copies)
                else:
                    # Full copies for remaining files
                    seq.extend([f] * self.copies)
            return seq
        else:
            # Collate Type 2: Set by Set (ABAB ABAB)
            # Print one copy of all files, then repeat
            seq = []
            for copy_idx in range(self.copies):
                if copy_idx < start_copy_index:
                    # Skip copies before resume point
                    continue
                elif copy_idx == start_copy_index:
                    # Partial set - start from specific file
                    seq.extend(files[start_file_index:])
                else:
                    # Full set of all files
                    seq.extend(files)
            return seq

    def _apply_all_filters_for_group(self, files: List[Path], settings: dict) -> List[Path]:
        """Apply range, odd/even, and reverse filters for a specific group"""
        result = files.copy()

        # Apply reverse first
        if settings.get('reverse', False):
            result = list(reversed(result))

        # Apply range filter
        range_mode = settings.get('range_mode', 'all')
        if range_mode == 'range':
            from_idx = settings['range_from']
            to_idx = settings['range_to']
            result = [f for idx, f in enumerate(result, start=1) if from_idx <= idx <= to_idx]
        elif range_mode == 'odd':
            result = [f for idx, f in enumerate(result, start=1) if idx % 2 == 1]
        elif range_mode == 'even':
            result = [f for idx, f in enumerate(result, start=1) if idx % 2 == 0]

        return result

    def _build_sequence_for_group(self, files: List[Path], copies: int, collate_type: int) -> List[Path]:
        """Build print sequence for a specific group"""
        if collate_type == 1:
            # Collate Type 1: File by File (AAAA BBBB)
            seq = []
            for f in files:
                seq.extend([f] * copies)
            return seq
        else:
            # Collate Type 2: Set by Set (ABAB ABAB)
            seq = []
            for _ in range(copies):
                seq.extend(files)
            return seq

    def _process_groups_for_server(
        self,
        tag: str,
        gui,
        group_settings: dict,
        print_order: List[str],
        folder: str,
        _cb,
        size_map: dict
    ) -> bool:
        """Process multiple groups with individual settings for a specific server (continuous printing)"""

        # Build all group sequences upfront and track boundaries
        master_sequence = []
        group_boundaries = []  # List of (group_name, start_idx, end_idx)
        current_position = 0

        for group_name in print_order:
            settings = group_settings[group_name]
            files = [Path(f) for f in settings['files']]
            filtered_files = self._apply_all_filters_for_group(files, settings)

            if not filtered_files:
                logger.warning(f"{tag}: Group '{group_name}' has no files after filtering, skipping")
                continue

            # Build sequence for this group
            group_sequence = self._build_sequence_for_group(
                filtered_files,
                settings['copies'],
                settings['collate_type']
            )

            # Track group boundary
            start_idx = current_position
            end_idx = current_position + len(group_sequence)
            group_boundaries.append((group_name, start_idx, end_idx))

            # Add to master sequence
            master_sequence.extend(group_sequence)
            current_position = end_idx

        total_pages = len(master_sequence)

        # Update server-specific total
        if tag == "server1":
            self._server1_total = total_pages
        else:
            self._server2_total = total_pages

        if not master_sequence:
            logger.warning(f"{tag}: No files to print after filtering all groups")
            return True

        # Handle resume logic
        resume_from = self.resume_server1_from if tag == "server1" else self.resume_server2_from
        resume_index = 0

        if resume_from > 0:
            resume_index = max(0, resume_from - self.repeat_resume_pages)
            # Update server-specific printed counter
            if tag == "server1":
                self._server1_printed = resume_index
            else:
                self._server2_printed = resume_index

            # Slice sequence from resume point
            if resume_index >= len(master_sequence):
                logger.info(f"{tag}: Resume from {resume_from} >= total {total_pages}, already complete")
                return True
            else:
                logger.info(f"{tag}: Resuming from page {resume_index + 1}/{total_pages} (re-printing last {self.repeat_resume_pages} pages)")
                master_sequence = master_sequence[resume_index:]

        # Convert to (path, size) tuples
        sequence_with_sizes = [(p, size_map.get(p, 0)) for p in master_sequence]

        # Wrap callback to show current group based on progress
        def continuous_callback(processed: int, total: int, message: str):
            if self._cancelled:
                return

            # Calculate actual processed count (accounting for resume)
            if processed <= 100 and total > 0:
                actual_progress = int((processed / 100.0) * total)
            else:
                actual_progress = min(processed, total)

            overall_processed = resume_index + actual_progress

            # Determine which group we're currently in
            # Note: Group boundaries are [start, end), so when overall_processed == end_idx,
            # the next group's start_idx will match. The elif handles completion of the last group.
            current_group_name = "Unknown"
            current_group_idx = 0
            for idx, (group_name, start_idx, end_idx) in enumerate(group_boundaries):
                if start_idx <= overall_processed < end_idx:
                    current_group_name = group_name
                    current_group_idx = idx
                    break
                elif overall_processed >= end_idx and idx == len(group_boundaries) - 1:
                    # Last group completed - we're at or past the end
                    current_group_name = group_name
                    current_group_idx = idx
                    break

            # Clean message to remove file counts
            import re
            clean_message = re.sub(r'\bQueued\s+\d+/\d+\s+files?\b', '', message, flags=re.IGNORECASE)
            clean_message = clean_message.strip() or message

            final_message = f"{tag.title()} - Group {current_group_idx + 1}/{len(group_boundaries)} ({current_group_name}): {clean_message}"
            _cb(overall_processed, total_pages, final_message)

            # NOTE: Do NOT update server printed counters here!
            # overall_processed represents files QUEUED/SENT, not PRINTED
            # Counters are updated from actual label events
            # Updating here causes resume to use queued count instead of printed count
            # if tag == "server1":
            #     self._server1_printed = overall_processed  # ❌ REMOVED - caused resume bug
            # else:
            #     self._server2_printed = overall_processed  # ❌ REMOVED - caused resume bug

        # Print entire merged sequence in ONE continuous session
        try:
            ok = gui.print_rip_folder_with_callback(
                folder, continuous_callback, pattern=self.pattern, recursive=False,
                num_copies=1, files_override=sequence_with_sizes,
                batch_size=self.batch_size
            )

            if not ok or self._cancelled:
                return False

        except Exception as e:
            logger.error(f"{tag}: Error printing groups: {e}")
            return False

        # Update final printed counter
        if tag == "server1":
            self._server1_printed = total_pages
        else:
            self._server2_printed = total_pages

        return True


