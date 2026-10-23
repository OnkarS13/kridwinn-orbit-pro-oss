import re
import time
from pathlib import Path
from typing import List
from PySide6.QtCore import QObject, Signal


def natural_sort_key(p: Path):
    parts = re.split(r'(\d+)', str(p.name))
    return [int(t) if t.isdigit() else t.lower() for t in parts]


class SingleServerWorker(QObject):
    """
    Discovers files, applies page range, builds sequence per collation, and iterates.
    This version does not talk to the server yet; it's for wiring and UI validation.
    """

    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(bool)
    error = Signal(str)

    def __init__(self, folder: str, pattern: str, copies: int,
                 collate_type: int, range_mode_all: bool,
                 range_from: int, range_to: int,
                 reverse_order: bool, continuous_mode: bool):
        super().__init__()
        self.folder = Path(folder)
        self.pattern = pattern
        self.copies = max(1, int(copies))
        self.collate_type = 1 if collate_type != 2 else 2
        self.range_mode_all = bool(range_mode_all)
        self.range_from = int(range_from)
        self.range_to = int(range_to)
        self.reverse_order = bool(reverse_order)
        self.continuous_mode = bool(continuous_mode)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            files = self._discover_files()
            if self.reverse_order:
                files = list(reversed(files))
            files = self._apply_page_range(files)
            sequence = self._build_sequence(files)

            total = len(sequence)
            if total == 0:
                self.progress.emit(0, 0, "No files to process")
                self.finished.emit(False)
                return

            for idx, f in enumerate(sequence, start=1):
                if self._cancelled:
                    self.progress.emit(idx - 1, total, "Cancelled")
                    self.finished.emit(False)
                    return
                # Simulate brief work; later this will be a print call
                time.sleep(0.01)
                self.progress.emit(idx, total, f"Queued: {f.name}")

            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)

    def _discover_files(self) -> List[Path]:
        if not self.folder.is_dir():
            return []
        files = list(self.folder.glob(self.pattern))
        files.sort(key=natural_sort_key)
        return files

    def _apply_page_range(self, files: List[Path]) -> List[Path]:
        if self.range_mode_all:
            return files
        lo = max(1, min(self.range_from, self.range_to))
        hi = max(self.range_from, self.range_to)
        sliced = []
        for i, f in enumerate(files, start=1):
            if lo <= i <= hi:
                sliced.append(f)
        return sliced

    def _build_sequence(self, files: List[Path]) -> List[Path]:
        if self.collate_type == 1:
            # Type 1: range then repeat copies
            return files * self.copies
        # Type 2: each file repeated N times before next
        seq: List[Path] = []
        for f in files:
            seq.extend([f] * self.copies)
        return seq


