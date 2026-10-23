"""
Production Logger
Handles automatic logging of print jobs to CSV files with daily/monthly/yearly aggregation
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import Optional


class ProductionLogger:
    """Manages production logging for print jobs"""
    
    def __init__(self):
        # Use centralized path helper for consistent path resolution
        from .path_helper import get_app_root
        app_root = get_app_root()
        
        # Use logs directory next to app.py/EXE
        self.logs_dir = app_root / "logs"
        
        # Create subdirectories for each mode
        self.daily_dir = self.logs_dir / "daily"
        self.monthly_dir = self.logs_dir / "monthly"
        self.yearly_dir = self.logs_dir / "yearly"
    
    def is_logging_enabled(self) -> bool:
        """
        Check if logging is enabled in admin settings
        
        Returns:
            True if logging is enabled, False otherwise
        """
        try:
            from .admin_config import AdminConfigManager
            config_manager = AdminConfigManager()
            settings = config_manager.load_settings()
            return settings.logging_enabled
        except Exception as e:
            print(f"Error checking logging status: {e}")
            return False
    
    def log_print_job(self, server: str, filename: str, pages: int, copies: int, mode: str):
        """
        Log a single print job to the appropriate CSV file
        
        Args:
            server: Server identifier (e.g., "Server1", "Server2", "Single")
            filename: Name of the printed file
            pages: Number of pages in the file
            copies: Number of copies printed
            mode: Print mode ("Single" or "Dual")
        """
        try:
            # Check if logging is enabled
            if not self.is_logging_enabled():
                return
            
            # Get logging mode from settings
            from .admin_config import AdminConfigManager
            config_manager = AdminConfigManager()
            settings = config_manager.load_settings()
            logging_mode = settings.logging_mode
            
            # Get the appropriate log file path
            log_file = self._get_log_file_path(logging_mode)
            
            # Ensure log file exists with headers
            self._ensure_log_file_exists(log_file)
            
            # Create log entry
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            total_prints = pages * copies
            
            entry = {
                'Timestamp': timestamp,
                'Server': server,
                'Filename': filename,
                'Pages': pages,
                'Copies': copies,
                'Total_Prints': total_prints,
                'Mode': mode
            }
            
            # Append to log file
            self._append_log_entry(log_file, entry)
            
        except Exception as e:
            print(f"Error logging print job: {e}")
    
    def _get_log_file_path(self, mode: str) -> Path:
        """
        Get the correct log file path based on mode and current date
        
        Args:
            mode: Logging mode ("daily", "monthly", or "yearly")
            
        Returns:
            Path to the log file
        """
        now = datetime.now()
        
        if mode == "daily":
            # Format: log_2025-11-24.csv
            filename = f"log_{now.strftime('%Y-%m-%d')}.csv"
            return self.daily_dir / filename
        
        elif mode == "monthly":
            # Format: log_2025-11.csv
            filename = f"log_{now.strftime('%Y-%m')}.csv"
            return self.monthly_dir / filename
        
        elif mode == "yearly":
            # Format: log_2025.csv
            filename = f"log_{now.strftime('%Y')}.csv"
            return self.yearly_dir / filename
        
        else:
            # Default to daily if mode is invalid
            filename = f"log_{now.strftime('%Y-%m-%d')}.csv"
            return self.daily_dir / filename
    
    def _ensure_log_file_exists(self, file_path: Path):
        """
        Create log file with CSV headers if it doesn't exist
        
        Args:
            file_path: Path to the log file
        """
        try:
            # Create parent directory if it doesn't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create file with headers if it doesn't exist
            if not file_path.exists():
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'Timestamp', 'Server', 'Filename', 'Pages', 'Copies', 'Total_Prints', 'Mode'
                    ])
                    writer.writeheader()
        
        except Exception as e:
            print(f"Error creating log file: {e}")
            raise
    
    def _append_log_entry(self, file_path: Path, entry: dict):
        """
        Append a log entry to the CSV file
        
        Args:
            file_path: Path to the log file
            entry: Dictionary containing log entry data
        """
        try:
            with open(file_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'Timestamp', 'Server', 'Filename', 'Pages', 'Copies', 'Total_Prints', 'Mode'
                ])
                writer.writerow(entry)
        
        except Exception as e:
            print(f"Error appending log entry: {e}")
            raise
