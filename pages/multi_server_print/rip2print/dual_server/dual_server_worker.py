import re
import time
from pathlib import Path
from typing import List, Tuple
from PySide6.QtCore import QObject, Signal


def natural_sort_key(p: Path):
    parts = re.split(r'(\d+)', str(p.name))
    return [int(t) if t.isdigit() else t.lower() for t in parts]


class DualServerWorker(QObject):
    """
    Discovers files for two servers (same folder → odd/even; or separate folders),
    applies page range, builds sequences per collation, and iterates (simulated).
    """

    progress = Signal(str, int, int, str)  # server_tag, current, total, message
    finished = Signal(bool)
    error = Signal(str)

    def __init__(self, same_folder: bool, folder1: str, folder2: str, pattern: str,
                 copies: int, collate_type: int, range_mode_all: bool,
                 range_from: int, range_to: int, reverse_order: bool):
        super().__init__()
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
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            if self.same_folder:
                all_files = self._discover(self.folder1)
                if self.reverse_order:
                    all_files = list(reversed(all_files))
                all_files = self._apply_page_range(all_files)
                odd_files, even_files = self._split_odd_even(all_files)
                seq1 = self._build_sequence(odd_files)
                seq2 = self._build_sequence(even_files)
            else:
                files1 = self._discover(self.folder1)
                files2 = self._discover(self.folder2)
                if self.reverse_order:
                    files1 = list(reversed(files1))
                    files2 = list(reversed(files2))
                files1 = self._apply_page_range(files1)
                files2 = self._apply_page_range(files2)
                seq1 = self._build_sequence(files1)
                seq2 = self._build_sequence(files2)

            total1, total2 = len(seq1), len(seq2)
            i1 = i2 = 0
            # Simulate parallel iteration by alternating
            while i1 < total1 or i2 < total2:
                if self._cancelled:
                    self.finished.emit(False)
                    return
                if i1 < total1:
                    time.sleep(0.005)
                    i1 += 1
                    self.progress.emit("server1", i1, total1, f"Queued: {seq1[i1-1].name}")
                if self._cancelled:
                    self.finished.emit(False)
                    return
                if i2 < total2:
                    time.sleep(0.005)
                    i2 += 1
                    self.progress.emit("server2", i2, total2, f"Queued: {seq2[i2-1].name}")

            self.finished.emit(True)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(False)

    def _discover(self, folder: Path) -> List[Path]:
        if not folder.is_dir():
            return []
        files = list(folder.glob(self.pattern))
        files.sort(key=natural_sort_key)
        return files

    def _apply_page_range(self, files: List[Path]) -> List[Path]:
        if self.range_mode_all:
            return files
        lo = max(1, min(self.range_from, self.range_to))
        hi = max(self.range_from, self.range_to)
        return [f for idx, f in enumerate(files, start=1) if lo <= idx <= hi]

    def _split_odd_even(self, files: List[Path]) -> Tuple[List[Path], List[Path]]:
        odd = [f for idx, f in enumerate(files, start=1) if idx % 2 == 1]
        even = [f for idx, f in enumerate(files, start=1) if idx % 2 == 0]
        return odd, even

    def _build_sequence(self, files: List[Path]) -> List[Path]:
        if self.collate_type == 1:
            return files * self.copies
        seq: List[Path] = []
        for f in files:
            seq.extend([f] * self.copies)
        return seq


