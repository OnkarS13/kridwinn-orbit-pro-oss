"""
Print Server Manager - Manages multiple printer server configurations (shared)
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional as TypingOptional
from PySide6.QtCore import QObject, Signal
from .server_config import PrinterServerConfig


logger = logging.getLogger(__name__)


class PrintServerManager(QObject):
    """Manages multiple printer server configurations"""

    server_added = Signal(str)  # server_id
    server_removed = Signal(str)  # server_id
    server_updated = Signal(str)  # server_id

    def __init__(self, config_file: str = "config/printer_servers.json"):
        super().__init__()
        self.servers: Dict[str, PrinterServerConfig] = {}
        self.config_file = Path(config_file)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing configurations
        self.load_config()

        # If no servers exist, create a default one
        if not self.servers:
            self.add_server("Default Server", "localhost", 2000)

    def add_server(self, name: str, ip: str, port: int) -> str:
        """Add a new server configuration"""
        # Prevent duplicate ip:port endpoints and duplicate ports
        if self._is_endpoint_in_use(ip, int(port)):
            raise ValueError(f"Server {ip}:{port} is already configured")
        if self._is_port_in_use(int(port)):
            raise ValueError(f"Port {port} is already in use by another server")
        server = PrinterServerConfig(name, ip, port)
        self.servers[server.id] = server
        self.save_config()
        self.server_added.emit(server.id)
        logger.info(f"Added server: {name} ({ip}:{port})")
        return server.id

    def remove_server(self, server_id: str) -> bool:
        """Remove a server configuration"""
        if server_id not in self.servers:
            return False

        server_name = self.servers[server_id].name
        del self.servers[server_id]
        self.save_config()
        self.server_removed.emit(server_id)
        logger.info(f"Removed server: {server_name}")
        return True

    def update_server(self, server_id: str, **kwargs):
        """Update server configuration"""
        if server_id not in self.servers:
            return False

        server = self.servers[server_id]
        # Validate endpoint uniqueness on changes
        if 'port' in kwargs:
            new_port = int(kwargs['port'])
            if self._is_port_in_use(new_port, exclude_id=server_id):
                logger.error(f"Port {new_port} is already in use")
                return False
        if 'ip' in kwargs or 'port' in kwargs:
            new_ip = kwargs.get('ip', server.ip)
            new_port = int(kwargs.get('port', server.port))
            if self._is_endpoint_in_use(new_ip, new_port, exclude_id=server_id):
                logger.error(f"Server {new_ip}:{new_port} is already configured")
                return False
        for key, value in kwargs.items():
            if hasattr(server, key):
                setattr(server, key, value)

        self.save_config()
        self.server_updated.emit(server_id)
        return True

    def get_server(self, server_id: str) -> TypingOptional[PrinterServerConfig]:
        """Get server configuration by ID"""
        return self.servers.get(server_id)

    def get_all_servers(self) -> Dict[str, PrinterServerConfig]:
        """Get all server configurations"""
        return self.servers.copy()

    def save_config(self):
        """Persist server configurations to file"""
        try:
            data = {sid: server.to_dict() for sid, server in self.servers.items()}
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self.servers)} server configs to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save server config: {e}")

    def load_config(self):
        """Load saved server configurations"""
        if not self.config_file.exists():
            logger.info("No existing server config file found")
            return

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.servers.clear()
            for sid, cfg in data.items():
                try:
                    server = PrinterServerConfig.from_dict(cfg)
                    self.servers[server.id] = server
                except Exception as e:
                    logger.error(f"Failed to load server config {sid}: {e}")

            logger.info(f"Loaded {len(self.servers)} server configurations")
        except Exception as e:
            logger.error(f"Failed to load server config file: {e}")

    # --- helpers ---
    def _is_port_in_use(self, port: int, exclude_id: TypingOptional[str] = None) -> bool:
        for sid, srv in self.servers.items():
            if exclude_id is not None and sid == exclude_id:
                continue
            try:
                if int(srv.port) == int(port):
                    return True
            except Exception:
                continue
        return False

    def _is_endpoint_in_use(self, ip: str, port: int, exclude_id: TypingOptional[str] = None) -> bool:
        endpoint = (str(ip).strip().lower(), int(port))
        for sid, srv in self.servers.items():
            if exclude_id is not None and sid == exclude_id:
                continue
            try:
                if (str(srv.ip).strip().lower(), int(srv.port)) == endpoint:
                    return True
            except Exception:
                continue
        return False


