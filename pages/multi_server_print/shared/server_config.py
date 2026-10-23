"""
Server Configuration Data Models (shared)
"""
import uuid
from typing import Dict, Any


class PrinterServerConfig:
    """Configuration for a single printer server"""

    def __init__(self, name: str = "New Server", ip: str = "localhost", port: int = 2000):
        self.id = str(uuid.uuid4())
        self.name = name
        self.ip = ip
        self.port = port
        self.enabled = True

        # Per-server settings
        self.rip_folder = ""
        self.num_copies = 1
        self.pattern = "*.bmp"
        self.recursive = False
        self.continuous_mode = False
        self.max_wait_time = 300

        # Page filter settings
        self.page_filter = {
            'mode': 'all',  # 'all', 'range', 'odd', 'even'
            'from': 1,
            'to': 1000000,
            'reverse': False,
            'odd': False,
            'even': False
        }

        # Runtime state (not saved)
        self.status = "idle"  # idle, connecting, printing, completed, error
        self.is_connected = False
        self.current_progress = 0
        self.total_files = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'ip': self.ip,
            'port': self.port,
            'enabled': self.enabled,
            'rip_folder': self.rip_folder,
            'num_copies': self.num_copies,
            'pattern': self.pattern,
            'recursive': self.recursive,
            'continuous_mode': self.continuous_mode,
            'max_wait_time': self.max_wait_time,
            'page_filter': self.page_filter
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PrinterServerConfig':
        """Create instance from dictionary"""
        server = cls(
            name=data.get('name', 'Server'),
            ip=data.get('ip', 'localhost'),
            port=data.get('port', 2000)
        )
        server.id = data.get('id', str(uuid.uuid4()))
        server.enabled = data.get('enabled', True)
        server.rip_folder = data.get('rip_folder', '')
        server.num_copies = data.get('num_copies', 1)
        server.pattern = data.get('pattern', '*.bmp')
        server.recursive = data.get('recursive', False)
        server.continuous_mode = data.get('continuous_mode', False)
        server.max_wait_time = data.get('max_wait_time', 300)
        server.page_filter = data.get('page_filter', {
            'mode': 'all',
            'from': 1,
            'to': 1000000,
            'reverse': False,
            'odd': False,
            'even': False
        })
        return server

    def __repr__(self):
        return f"PrinterServerConfig(name='{self.name}', ip='{self.ip}', port={self.port})"


