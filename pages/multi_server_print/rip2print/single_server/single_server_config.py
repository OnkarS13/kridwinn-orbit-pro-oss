from dataclasses import dataclass
from pathlib import Path


@dataclass
class SingleServerConfig:
    server_id: str
    server_name: str
    server_ip: str
    server_port: int
    rip_folder: str
    file_pattern: str
    num_copies: int
    collation_type: int  # 1 or 2
    page_range_mode: str  # "all" or "specify"
    page_range_from: int
    page_range_to: int
    order_mode: str  # "normal", "reverse", "continuous"
    max_wait_time: int = 300

    def validate(self) -> None:
        if not self.server_ip:
            raise ValueError("server_ip is required")
        if not isinstance(self.server_port, int) or self.server_port <= 0:
            raise ValueError("server_port must be a positive integer")
        if not self.rip_folder or not Path(self.rip_folder).is_dir():
            raise ValueError("rip_folder must be an existing directory")
        if self.file_pattern not in ("*.bmp", "*.BMP", "*.tiff", "*.TIFF"):
            raise ValueError("file_pattern must be one of BMP/TIFF variants")
        if not isinstance(self.num_copies, int) or self.num_copies < 1:
            raise ValueError("num_copies must be >= 1")
        if self.collation_type not in (1, 2):
            raise ValueError("collation_type must be 1 or 2")
        if self.page_range_mode not in ("all", "specify"):
            raise ValueError("page_range_mode must be 'all' or 'specify'")
        if self.page_range_mode == "specify":
            lo = max(1, min(self.page_range_from, self.page_range_to))
            hi = max(self.page_range_from, self.page_range_to)
            if lo > hi:
                raise ValueError("invalid page range")
        if self.order_mode not in ("normal", "reverse", "continuous"):
            raise ValueError("order_mode must be normal|reverse|continuous")

    def to_dict(self) -> dict:
        return {
            "server_id": self.server_id,
            "server_name": self.server_name,
            "server_ip": self.server_ip,
            "server_port": self.server_port,
            "rip_folder": self.rip_folder,
            "file_pattern": self.file_pattern,
            "num_copies": self.num_copies,
            "collation_type": self.collation_type,
            "page_range_mode": self.page_range_mode,
            "page_range_from": self.page_range_from,
            "page_range_to": self.page_range_to,
            "order_mode": self.order_mode,
            "max_wait_time": self.max_wait_time,
        }

    @classmethod
    def from_dict(cls, data: dict):
        inst = cls(
            server_id=data.get("server_id", ""),
            server_name=data.get("server_name", ""),
            server_ip=data.get("server_ip", ""),
            server_port=int(data.get("server_port", 2000)),
            rip_folder=data.get("rip_folder", ""),
            file_pattern=data.get("file_pattern", "*.bmp"),
            num_copies=int(data.get("num_copies", 1)),
            collation_type=int(data.get("collation_type", 1)),
            page_range_mode=data.get("page_range_mode", "all"),
            page_range_from=int(data.get("page_range_from", 1)),
            page_range_to=int(data.get("page_range_to", 1_000_000)),
            order_mode=data.get("order_mode", "normal"),
            max_wait_time=int(data.get("max_wait_time", 300)),
        )
        return inst


