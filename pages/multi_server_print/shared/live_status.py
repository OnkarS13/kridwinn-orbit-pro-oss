from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class LiveStatusData:
    files_sent: int = 0
    files_printed: int = 0
    total_files: int = 0
    speed_mpm: Optional[float] = None
    start_time: Optional[datetime] = None
    last_update: Optional[datetime] = None
    current_file: str = ""

    @property
    def sent_percentage(self) -> int:
        return int((self.files_sent / self.total_files) * 100) if self.total_files else 0

    @property
    def printed_percentage(self) -> int:
        return int((self.files_printed / self.total_files) * 100) if self.total_files else 0

    @property
    def lag(self) -> int:
        return max(0, self.files_sent - self.files_printed)

    @property
    def elapsed_time(self) -> float:
        if self.start_time and self.last_update:
            return (self.last_update - self.start_time).total_seconds()
        return 0.0

    def reset(self) -> None:
        self.files_sent = 0
        self.files_printed = 0
        self.total_files = 0
        self.speed_mpm = None
        self.start_time = None
        self.last_update = None
        self.current_file = ""


