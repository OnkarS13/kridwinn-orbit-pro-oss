import logging
from pathlib import Path
from typing import List, Tuple, Optional
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class SingleServerPrintWorkerReal(QObject):
    """
    Real Single-Server printing worker using GUIRipPrinter and RIPFolderPrinter.
    Runs inside a QThread. Emits progress, error, finished, and status_update.
    """

    progress = Signal(int, int, str)  # processed, total, message
    finished = Signal(bool)           # success
    error = Signal(str)
    status_update = Signal(dict)      # {sent, printed, total, speed}
    error_occurred = Signal(dict)     # {error_msg, sent, printed, total} - detailed error info
    server_error_detected = Signal(dict)  # {error_type, error_msg, last_printed, total, can_resume} - server errors with auto-save

    def __init__(
        self,
        server_ip: str,
        server_port: int,
        rip_folder: str,
        pattern: str,
        copies: int,
        collate_type: int,
        range_mode_all: bool,
        range_from: int,
        range_to: int,
        reverse_order: bool,
        continuous_mode: bool,
        resume_from_page: int = 0,
        files_list: list = None,
        batch_size: int = 10,
        repeat_resume_pages: int = 1,
        group_settings: dict = None,
        print_order: list = None,
    ):
        super().__init__()
        self.server_ip = server_ip
        self.server_port = int(server_port)
        self.rip_folder = Path(rip_folder)
        self.pattern = pattern
        self.copies = max(1, int(copies))
        self.collate_type = 1 if collate_type != 2 else 2
        self.range_mode_all = bool(range_mode_all)
        self.range_from = int(range_from)
        self.range_to = int(range_to)
        self.reverse_order = bool(reverse_order)
        self.continuous_mode = bool(continuous_mode)
        self.resume_from_page = max(0, int(resume_from_page))
        self.files_list = files_list  # Pre-filtered file list (for file grouping)
        self.batch_size = max(1, int(batch_size))
        # How many previously printed pages to re-send when resuming
        self.repeat_resume_pages = max(0, int(repeat_resume_pages))
        # Per-group settings for advanced file grouping
        self.group_settings = group_settings  # Dict[group_name, settings]
        self.print_order = print_order  # List[group_name] - order of groups
        self._cancelled = False

        self._sent = 0
        self._printed = 0
        self._total = 0
        # Initialize label offset to resume point - adjusted for F.a fix (re-print last N pages)
        # If resuming from page 5 with repeat_resume_pages=2, we start at page 3
        if self.resume_from_page > 0 and self.repeat_resume_pages > 0:
            self._label_offset = max(0, self.resume_from_page - self.repeat_resume_pages)
        else:
            self._label_offset = 0
        self._last_label = 0
        self._last_printed_label = 0
        self._current_speed = None
        self._last_emitted_label = -1  # Track last emitted label to avoid duplicates

        # Error detection tracking
        self._last_traffic_code = None
        self._last_status_code = None
        self._error_detected = False

        # Resume state tracking
        self.resume_state = None  # Will store state when stopped

    def _save_resume_state(self, reason="manual"):
        """Save resume state for later continuation"""
        self.resume_state = {
            'last_printed': self._printed,
            'total': self._total,
            'folder_path': str(self.rip_folder),
            'server_ip': self.server_ip,
            'server_port': self.server_port,
            'pattern': self.pattern,
            'copies': self.copies,
            'collate_type': self.collate_type,
            'range_mode_all': self.range_mode_all,
            'range_from': self.range_from,
            'range_to': self.range_to,
            'reverse_order': self.reverse_order,
            'continuous_mode': self.continuous_mode,
            'batch_size': self.batch_size,
            'files_list': [str(f) for f in self.files_list] if self.files_list else None,
            'group_settings': self.group_settings,
            'print_order': self.print_order,
        }
        logger.info(f"Resume state saved ({reason}): last_printed={self._printed}/{self._total}")

    def cancel(self):
        """Cancel the print job and abort server operations"""
        self._cancelled = True

        # Save resume state when stopping
        self._save_resume_state(reason="manual_cancel")

        try:
            # Try to abort the print server if we have a connection
            if hasattr(self, '_gui') and self._gui and getattr(self._gui, 'client', None):
                try:
                    # Cancel the printer instance if it exists
                    if hasattr(self._gui, 'printer') and self._gui.printer:
                        self._gui.printer.cancel()
                    # Send abort command to the print server
                    if hasattr(self._gui.client, 'abort_print'):
                        self._gui.client.abort_print()
                    # Close the connection to interrupt any ongoing operations
                    self._gui.close()
                except Exception:
                    pass
        except Exception:
            pass

    def _handle_server_error(self, error_type: str, error_msg: str):
        """Handle server errors with auto-save and notification"""
        if self._error_detected:
            return  # Already handling an error

        self._error_detected = True

        # Save resume state automatically
        self._save_resume_state(reason=f"server_error_{error_type}")

        # Emit detailed error signal for UI
        error_details = {
            'error_type': error_type,
            'error_msg': error_msg,
            'last_printed': self._printed,
            'total': self._total,
            'can_resume': True,
            'resume_from': max(0, self._printed - self.repeat_resume_pages) if self.repeat_resume_pages > 0 else self._printed
        }

        logger.error(f"Server error detected: {error_type} - {error_msg} at page {self._printed}/{self._total}")

        # Emit both signals for compatibility
        self.error_occurred.emit({
            'error_msg': f"Server Error ({error_type}): {error_msg}",
            'sent': self._sent,
            'printed': self._printed,
            'total': self._total
        })
        self.server_error_detected.emit(error_details)

        # Mark as cancelled to stop further processing
        self._cancelled = True

    def run(self):
        from pages.rip_to_print.rip_to_print import GUIRipPrinter, RIPFolderPrinter

        if not self.rip_folder.is_dir():
            error_msg = "RIP folder not found"
            self.error.emit(error_msg)
            self.error_occurred.emit({
                'error_msg': error_msg,
                'sent': 0,
                'printed': 0,
                'total': self._total
            })
            self.finished.emit(False)
            return

        # Continuous mode support

        gui = None
        try:
            gui = GUIRipPrinter(self.server_ip, self.server_port)
            # retain for abort
            self._gui = gui
            if not gui.connect():
                error_msg = f"Failed to connect to {self.server_ip}:{self.server_port}"
                self.error.emit(error_msg)
                self.error_occurred.emit({
                    'error_msg': error_msg,
                    'sent': 0,
                    'printed': 0,
                    'total': self._total
                })
                self.finished.emit(False)
                return

            # Attempt to establish dedicated status client for live printed counts
            # Register for live status events (label counts, etc.)
            try:
                gui.client.add_status_listener(self._handle_status_event)
            except Exception as status_err:
                logger.debug(f"Unable to register status listener: {status_err}")

            def _cb(processed: int, total: int, message: str):
                # The callback from RIPFolderPrinter passes percentage (0-100) during progress updates
                # We need to get the actual sent/printed counts properly
                actual_total = self._total if self._total > 0 else total

                estimated_sent = self._sent
                estimated_printed = self._printed
                try:
                    # Try to extract actual counts from message like "Queued 50/100 files"
                    import re
                    match = re.search(r'Queued\s+(\d+)/(\d+)', message)
                    if match:
                        estimated_sent = int(match.group(1))
                        estimated_printed = min(estimated_sent, estimated_printed + 1)  # Estimate printed
                    elif "completed" in message.lower() or "finished" in message.lower():
                        # Completion message - set to total
                        estimated_sent = actual_total
                        estimated_printed = actual_total
                    else:
                        # Try to get actual counts from the printer instance
                        if hasattr(gui, 'printer') and gui.printer:
                            estimated_sent = getattr(gui.printer, 'total_files_sent', 0)
                            estimated_printed = getattr(gui.printer, 'total_files_acked', 0)
                        else:
                            # Fallback: estimate from percentage if processed looks like 0-100
                            if processed <= 100 and actual_total > 0:
                                sent = int((processed / 100.0) * actual_total)
                                estimated_sent = max(estimated_sent, sent)  # Don't go backwards
                            else:
                                estimated_sent = min(processed, actual_total)  # Cap at total
                            estimated_printed = estimated_sent  # Conservative estimate
                except Exception:
                    # Ultimate fallback
                    if processed <= 100 and actual_total > 0:
                        sent = int((processed / 100.0) * actual_total)
                        estimated_sent = max(estimated_sent, sent)
                    else:
                        estimated_sent = min(processed, actual_total)
                    estimated_printed = estimated_sent

                # Ensure values don't exceed total
                self._sent = min(actual_total, max(self._sent, estimated_sent))
                
                # For printed count, use the real label events (self._last_printed_label)
                # as the authoritative source, independent of sent count
                real_printed = self._last_printed_label + self._label_offset
                self._printed = min(actual_total, max(self._printed, real_printed))
                
                # Emit progress using actual counts
                self.progress.emit(self._printed, actual_total, message)
                
                # Fetch speed and emit status update
                speed_val = self._fetch_speed(gui)
                self._emit_status_update(actual_total, speed_val)

            # Check if per-group mode is enabled
            if self.group_settings and self.print_order:
                # PER-GROUP MODE: Process each group with individual settings
                success = self._process_groups(gui, RIPFolderPrinter, _cb)
            elif self.continuous_mode:
                # Use printer's continuous mode if available
                try:
                    success = gui.print_rip_folder_continuous_with_callback(
                        str(self.rip_folder),
                        _cb,
                        pattern=self.pattern,
                        recursive=False,
                        num_copies=self.copies,
                        max_wait_time=300,
                        batch_size=self.batch_size
                    )
                except AttributeError:
                    # Fallback: single pass if API missing
                    success = self._single_pass(gui, RIPFolderPrinter, _cb)
            else:
                success = self._single_pass(gui, RIPFolderPrinter, _cb)

            self.finished.emit(bool(success))

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
                self._handle_server_error(error_type, detailed_msg)

            # Emit legacy error signal for compatibility
            self.error.emit(error_msg)

            # Emit detailed error info with last known counts
            self.error_occurred.emit({
                'error_msg': error_msg,
                'sent': self._sent,
                'printed': self._printed,
                'total': self._total
            })

            self.finished.emit(False)
        finally:
            if gui:
                try:
                    try:
                        gui.client.remove_status_listener(self._handle_status_event)
                    except Exception:
                        pass
                    gui.close()
                except Exception:
                    pass
            self._gui = None

    def _apply_page_range(self, files: List[Path]) -> List[Path]:
        if self.range_mode_all:
            return files
        lo = max(1, min(self.range_from, self.range_to))
        hi = max(self.range_from, self.range_to)
        return [f for idx, f in enumerate(files, start=1) if lo <= idx <= hi]

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

    def _single_pass(self, gui, RIPFolderPrinter, cb) -> bool:
        # Use pre-filtered files if provided (from file grouping), otherwise discover
        temp = RIPFolderPrinter(gui.client, batch_size=self.batch_size)

        if self.files_list is not None:
            # Use pre-filtered file list (from file grouping feature)
            files = [Path(f) for f in self.files_list]
            # Get file sizes for the filtered files
            size_map = {}
            for f in files:
                try:
                    size_map[f] = f.stat().st_size
                except Exception:
                    size_map[f] = 0
        else:
            # Normal flow: discover all files from folder
            files_with_sizes: List[Tuple[Path, int]] = temp.discover_rip_files(
                str(self.rip_folder), pattern=self.pattern, recursive=False
            )
            # Build size map for later
            size_map = {p: s for (p, s) in files_with_sizes}
            files = [p for (p, _s) in files_with_sizes]

        # Apply reverse order and page range to ALL files (regardless of source)
        if self.reverse_order:
            files = list(reversed(files))
        files = self._apply_page_range(files)

        if not files:
            self.error.emit("No RIP files found after filtering")
            return False
        
        # Emit clarifying message about actual file count before copies
        unique_file_count = len(files)
        if self.copies > 1:
            self.progress.emit(0, 0, f"Processing {unique_file_count} unique files × {self.copies} copies = {unique_file_count * self.copies} total prints")

        # Handle resume with copies logic (F.a + F.d)
        start_file_index = 0
        start_copy_index = 0

        if self.resume_from_page > 0 and self.copies > 1:
            # F.d: Resume with copies - calculate (file_index, copy_index)
            # Re-print last N pages for safety (go back repeat_resume_pages from resume_from_page)
            back_count = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
            resume_index = max(0, self.resume_from_page - back_count)
            num_files = len(files)

            if self.collate_type == 1:
                # Collate Type 1: File by File (AAAA BBBB)
                start_file_index = resume_index // self.copies
                start_copy_index = resume_index % self.copies
                logger.info(f"Resuming from File {start_file_index + 1}, Copy {start_copy_index + 1} (Collate Type 1: File by File)")
            else:
                # Collate Type 2: Set by Set (ABAB ABAB)
                start_copy_index = resume_index // num_files
                start_file_index = resume_index % num_files
                logger.info(f"Resuming from Copy {start_copy_index + 1}, File {start_file_index + 1} (Collate Type 2: Set by Set)")

            # Build sequence starting from calculated position
            sequence = self._build_sequence(files, start_file_index, start_copy_index)
            # Calculate original total for proper progress tracking
            self._total = num_files * self.copies
            # Set printed counter to resume point
            self._printed = resume_index

        elif self.resume_from_page > 0:
            # F.a: Simple resume (no copies, or copies=1)
            back_count = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
            resume_index = max(0, self.resume_from_page - back_count)

            # Build full sequence first
            sequence = self._build_sequence(files)
            self._total = len(sequence)

            if resume_index >= len(sequence):
                logger.info(f"Resume from page {self.resume_from_page} >= total {len(sequence)}, nothing to print")
                return True  # Job already complete

            if self.repeat_resume_pages > 0:
                logger.info(
                    f"Resuming from page {resume_index + 1}/{len(sequence)} "
                    f"(re-printing last {self.repeat_resume_pages} page(s) for safety)"
                )
            else:
                logger.info(f"Resuming from page {resume_index + 1}/{len(sequence)} (no re-print on resume)")
            sequence = sequence[resume_index:]
            self._printed = resume_index
        else:
            # Normal start (no resume)
            sequence = self._build_sequence(files)
            self._total = len(sequence)
        
        # Convert sequence back to (path, size) tuples
        # Ensure all paths are Path objects (defensive programming for edge cases)
        sequence_with_sizes = [(Path(p) if not isinstance(p, Path) else p, size_map.get(p, 0)) for p in sequence]
        
        try:
            return gui.print_rip_folder_with_callback(
                str(self.rip_folder),
                cb,
                pattern=self.pattern,
                recursive=False,
                num_copies=1,  # Always 1 since sequence already contains copies
                files_override=sequence_with_sizes,
                batch_size=self.batch_size
            )
        except Exception as e:
            # Handle any errors during printing (including socket errors from cancel)
            if not self._cancelled:
                logger.error(f"Print error: {e}")
            return False

    def _process_groups(self, gui, RIPFolderPrinter, cb) -> bool:
        """
        Process multiple groups with individual settings (continuous printing).

        Builds all group sequences upfront and prints them in ONE continuous session
        to avoid printer reinitialization between groups.
        """
        # Build all group sequences upfront and track boundaries
        master_sequence = []
        group_boundaries = []  # List of (group_name, start_idx, end_idx)
        current_position = 0
        size_map = {}

        for group_name in self.print_order:
            settings = self.group_settings[group_name]
            files = [Path(f) for f in settings['files']]

            # Apply all filters (range, odd/even, reverse)
            filtered_files = self._apply_all_filters(files, settings)

            if not filtered_files:
                logger.warning(f"Group '{group_name}' has no files after filtering, skipping")
                continue

            # Build sequence with copies and collation for this group
            group_sequence = self._build_group_sequence(filtered_files, settings)

            # Track group boundary
            start_idx = current_position
            end_idx = current_position + len(group_sequence)
            group_boundaries.append((group_name, start_idx, end_idx))

            # Add to master sequence
            master_sequence.extend(group_sequence)
            current_position = end_idx

            # Collect file sizes
            for f in filtered_files:
                if f not in size_map:
                    try:
                        size_map[f] = f.stat().st_size
                    except Exception:
                        size_map[f] = 0

        total_pages = len(master_sequence)
        self._total = total_pages

        if not master_sequence:
            logger.warning("No files to print after filtering all groups")
            return True

        # Handle resume logic
        resume_index = 0
        if self.resume_from_page > 0:
            back_count = self.repeat_resume_pages if self.repeat_resume_pages > 0 else 0
            resume_index = max(0, self.resume_from_page - back_count)

            if resume_index >= total_pages:
                logger.info(f"Resume from page {self.resume_from_page} >= total {total_pages}, nothing to print")
                return True

            logger.info(f"Resuming from page {resume_index + 1}/{total_pages} (re-printing last {self.repeat_resume_pages} pages)")
            # Set printed counter to resume point
            self._printed = resume_index
            # Slice sequence from resume point
            master_sequence = master_sequence[resume_index:]
            # Emit initial message
            self.progress.emit(resume_index, total_pages, f"Resuming from page {resume_index + 1}/{total_pages}")
        else:
            # Normal start
            self.progress.emit(0, total_pages, f"Processing {len(group_boundaries)} group(s), {total_pages} total prints")

        # Convert to (path, size) tuples
        sequence_with_sizes = [(p, size_map.get(p, 0)) for p in master_sequence]

        # Wrap callback to show current group based on progress
        def continuous_callback(processed: int, total: int, message: str):
            """Track which group we're in based on progress"""
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
            clean_message = re.sub(r'\b\d+/\d+\s+files?\b', '', clean_message, flags=re.IGNORECASE)
            clean_message = clean_message.strip() or message

            final_message = f"Group {current_group_idx + 1}/{len(group_boundaries)} ({current_group_name}): {clean_message}"
            cb(overall_processed, total_pages, final_message)

            # NOTE: Do NOT update self._printed here!
            # overall_processed represents files QUEUED/SENT, not PRINTED
            # self._printed is updated from actual label events at line 778
            # Updating here causes resume to use queued count instead of printed count
            # self._printed = overall_processed  # ❌ REMOVED - caused resume bug

        # Print entire merged sequence in ONE continuous session
        try:
            success = gui.print_rip_folder_with_callback(
                str(self.rip_folder),
                continuous_callback,
                pattern=self.pattern,
                recursive=False,
                num_copies=1,  # Always 1 since sequence already contains copies
                files_override=sequence_with_sizes,
                batch_size=self.batch_size
            )

            if not success:
                logger.error("Failed to print groups")
                return False

        except Exception as e:
            if not self._cancelled:
                logger.error(f"Error printing groups: {e}")
            return False

        # Update final printed counter
        self._printed = total_pages
        self.progress.emit(total_pages, total_pages, f"✓ Completed all {len(group_boundaries)} groups"
            )

        return True

    def _apply_all_filters(self, files: List[Path], settings: dict) -> List[Path]:
        """
        Apply all filters to a list of files based on group settings.
        Filters: reverse order, range mode, odd/even
        """
        result = files[:]

        # Apply reverse order first (affects indexing)
        if settings.get('reverse', False):
            result = list(reversed(result))

        # Apply range/odd/even filtering
        range_mode = settings.get('range_mode', 'all')

        if range_mode == 'all':
            # No filtering needed
            pass
        elif range_mode == 'range':
            # Apply range filter
            range_from = settings.get('range_from', 1)
            range_to = settings.get('range_to', len(result))
            lo = max(1, min(range_from, range_to))
            hi = min(len(result), max(range_from, range_to))
            result = [f for idx, f in enumerate(result, start=1) if lo <= idx <= hi]
        elif range_mode == 'odd':
            # Keep only odd-indexed pages (1, 3, 5, ...)
            result = [f for idx, f in enumerate(result, start=1) if idx % 2 == 1]
        elif range_mode == 'even':
            # Keep only even-indexed pages (2, 4, 6, ...)
            result = [f for idx, f in enumerate(result, start=1) if idx % 2 == 0]

        return result

    def _build_group_sequence(self, files: List[Path], settings: dict) -> List[Path]:
        """
        Build print sequence for a single group based on its settings.
        Applies copies and collation type.
        """
        copies = settings.get('copies', 1)
        collate_type = settings.get('collate_type', 1)

        if collate_type == 1:
            # Collate Type 1: File by File (AAAA BBBB)
            # Print all copies of file A, then all copies of file B
            sequence = []
            for f in files:
                sequence.extend([f] * copies)
            return sequence
        else:
            # Collate Type 2: Set by Set (ABAB ABAB)
            # Print one copy of all files, then repeat
            sequence = []
            for _ in range(copies):
                sequence.extend(files)
            return sequence

    def _fetch_speed(self, gui) -> Optional[float]:
        try:
            status = gui.client.get_current_status()
            if isinstance(status, dict):
                speed_val = status.get('speed_mpm')
                if speed_val is not None:
                    speed_val = float(speed_val)
                    self._current_speed = speed_val
                    return speed_val
        except Exception:
            pass
        return self._current_speed

    def _emit_status_update(self, total: int, speed: Optional[float] = None):
        if speed is not None:
            self._current_speed = speed
        else:
            speed = self._current_speed

        payload = {
            'sent': self._sent,
            'printed': min(self._printed, total) if total else self._printed,
            'total': total
        }
        if speed is not None:
            payload['speed'] = speed
        self.status_update.emit(payload)

    def _handle_status_event(self, event: dict):
        if not isinstance(event, dict):
            return
        if event.get('category') != 'print':
            return
        evt = event.get('event')

        # ERROR DETECTION: Traffic light code 3 indicates error
        if evt == 'traffic':
            traffic_code = event.get('code')
            self._last_traffic_code = traffic_code
            if traffic_code == 3:  # Error state
                self._handle_server_error(
                    error_type="TRAFFIC_LIGHT_ERROR",
                    error_msg="Server reported traffic light error (code 3)"
                )
                return

        # ERROR DETECTION: Status error codes
        elif evt == 'status':
            status_code = event.get('code')
            status_text = event.get('text', '')
            self._last_status_code = status_code

            # Error codes from GIS documentation
            ERROR_STATUS_CODES = {
                4: "Init PMB Error",
                9: "Transport Failed",
                19: "Security Failed"
            }

            if status_code in ERROR_STATUS_CODES:
                self._handle_server_error(
                    error_type=f"STATUS_ERROR_{status_code}",
                    error_msg=f"{ERROR_STATUS_CODES[status_code]}: {status_text}"
                )
                return

        # NORMAL EVENTS: Label printing
        elif evt == 'label':
            label = event.get('label')
            if label is None:
                return
            # Detect printer restart (label count goes backwards)
            # But don't double-count the resume_from_page offset
            if label < self._last_label and self._last_label > 0:
                # Printer restarted its counter - add the previous max to offset
                self._label_offset += self._last_label
            self._last_label = label
            self._last_printed_label = label  # Track for error detection
            printed = self._label_offset + label
            if printed < 0:
                printed = label
            self._printed = max(self._printed, printed)
            if self._total:
                # Emit progress message only if label changed (deduplicate)
                if printed != self._last_emitted_label:
                    self._last_emitted_label = printed
                    self.progress.emit(self._printed, self._total, f"Printed label {printed}")
                self._emit_status_update(self._total)

                # Safety check: If we've printed all expected pages, log completion
                if self._printed >= self._total:
                    logger.info(f"Safety check: Reached completion ({self._printed}/{self._total}) - all copies printed")

        elif evt == 'end_print':
            if self._total:
                self._printed = max(self._printed, self._total)
                self._emit_status_update(self._total)
                # Safety check: If all copies are printed, ensure termination
                # This is a defensive measure in case the underlying library doesn't stop cleanly
                if self._printed >= self._total:
                    logger.info(f"Safety check: All copies complete ({self._printed}/{self._total}), ensuring clean termination")
                    # Note: We don't call cancel() here as it would trigger resume state saving
                    # The underlying library should handle termination, this is just logging for awareness

        elif evt == 'speed':
            speed_val = event.get('speed_mpm')
            if speed_val is None:
                return
            try:
                speed_val = float(speed_val)
            except (TypeError, ValueError):
                return
            self._current_speed = speed_val
            self._emit_status_update(self._total, speed_val)



