from dataclasses import dataclass
from pathlib import Path


@dataclass
class DualServerConfig:
    server1_id: str
    server2_id: str
    server1_name: str
    server2_name: str
    server1_ip: str
    server1_port: int
    server2_ip: str
    server2_port: int
    same_folder: bool
    folder1: str
    folder2: str
    file_pattern: str
    num_copies: int
    collation_type: int
    page_range_mode: str
    page_range_from: int
    page_range_to: int
    reverse_order: bool

    def validate(self) -> None:
        if self.server1_id == self.server2_id:
            raise ValueError("Servers must be different for dual printing")
        if not Path(self.folder1).is_dir():
            raise ValueError("folder1 must exist")
        if not self.same_folder and not Path(self.folder2).is_dir():
            raise ValueError("folder2 must exist when not using same_folder")
        if self.file_pattern not in ("*.bmp", "*.BMP", "*.tiff", "*.TIFF"):
            raise ValueError("file_pattern must be one of BMP/TIFF variants")
        if self.num_copies < 1:
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

    def to_dict(self) -> dict:
        return {
            "server1_id": self.server1_id,
            "server2_id": self.server2_id,
            "server1_name": self.server1_name,
            "server2_name": self.server2_name,
            "server1_ip": self.server1_ip,
            "server1_port": self.server1_port,
            "server2_ip": self.server2_ip,
            "server2_port": self.server2_port,
            "same_folder": self.same_folder,
            "folder1": self.folder1,
            "folder2": self.folder2,
            "file_pattern": self.file_pattern,
            "num_copies": self.num_copies,
            "collation_type": self.collation_type,
            "page_range_mode": self.page_range_mode,
            "page_range_from": self.page_range_from,
            "page_range_to": self.page_range_to,
            "reverse_order": self.reverse_order,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            server1_id=data.get("server1_id", ""),
            server2_id=data.get("server2_id", ""),
            server1_name=data.get("server1_name", ""),
            server2_name=data.get("server2_name", ""),
            server1_ip=data.get("server1_ip", ""),
            server1_port=int(data.get("server1_port", 2000)),
            server2_ip=data.get("server2_ip", ""),
            server2_port=int(data.get("server2_port", 2000)),
            same_folder=bool(data.get("same_folder", True)),
            folder1=data.get("folder1", ""),
            folder2=data.get("folder2", ""),
            file_pattern=data.get("file_pattern", "*.bmp"),
            num_copies=int(data.get("num_copies", 1)),
            collation_type=int(data.get("collation_type", 1)),
            page_range_mode=data.get("page_range_mode", "all"),
            page_range_from=int(data.get("page_range_from", 1)),
            page_range_to=int(data.get("page_range_to", 1_000_000)),
            reverse_order=bool(data.get("reverse_order", False)),
        )


