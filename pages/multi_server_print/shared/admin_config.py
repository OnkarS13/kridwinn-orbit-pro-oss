"""
Admin Configuration
Data model and persistence for admin panel settings
"""

import json
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class AdminSettings:
    """Admin panel settings data model"""
    
    # File Management
    fix_browse_folder: bool = False
    fixed_folder_path: str = ""  # For Single Server & Dual Server Folder 1
    fixed_folder_path_2: str = ""  # For Dual Server Folder 2 (separate mode)
    auto_refresh_enabled: bool = False
    auto_refresh_interval: int = 5  # seconds
    
    # Operator Controls
    enable_copies_collate: bool = True
    enable_specify_range: bool = True
    enable_reverse_order: bool = True
    enable_continuous_mode: bool = True
    
    # Post-Print Actions
    post_print_action: str = "no_action"  # no_action, delete, move
    move_destination: str = ""
    move_destination_2: str = ""  # For Dual Server (Folder 2)
    
    # Logging
    logging_enabled: bool = False
    logging_mode: str = "daily"  # daily, monthly, yearly
    
    
    # Reprint Detection
    enable_reprint_detection: bool = False
    reprint_mode: str = "allowed"  # allowed, warning, not_allowed
    history_retention_days: int = 30  # Auto-delete records older than this
    
    # File Grouping
    enable_file_grouping: bool = True  # Enable multi-PDF file grouping feature
    
    # Print Queue Performance
    batch_size: int = 10  # Number of files to send to printer queue at once (1-50)
    
    # Resume behavior
    # How many previously printed pages should be re-sent when resuming a stopped job
    # Default: 1 (current behavior)
    resume_repeat_pages: int = 1
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AdminSettings':
        """Create from dictionary, handling missing keys gracefully"""
        # Get default values and update with saved data
        # This ensures backward compatibility when new fields are added
        defaults = asdict(cls())
        defaults.update(data)
        return cls(**defaults)


class AdminConfigManager:
    """Manages admin settings persistence"""
    
    def __init__(self):
        # Use centralized path helper for consistent path resolution
        from .path_helper import get_app_root
        app_root = get_app_root()
        
        # Use config directory for settings storage
        self.config_dir = app_root / "config"
        self.settings_file = self.config_dir / "admin_settings.json"
        
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_settings(self) -> AdminSettings:
        """
        Load admin settings from file
        
        Returns:
            AdminSettings object (defaults if file doesn't exist)
        """
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                return AdminSettings.from_dict(data)
            else:
                # Return default settings
                return AdminSettings()
                
        except Exception as e:
            print(f"Error loading admin settings: {e}")
            # Return default settings on error
            return AdminSettings()
    
    def save_settings(self, settings: AdminSettings) -> bool:
        """
        Save admin settings to file
        
        Args:
            settings: AdminSettings object to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as file:
                json.dump(settings.to_dict(), file, indent=2)
            return True
            
        except Exception as e:
            print(f"Error saving admin settings: {e}")
            return False
    
    def reset_settings(self) -> bool:
        """
        Reset settings to defaults
        
        Returns:
            True if successful, False otherwise
        """
        try:
            default_settings = AdminSettings()
            return self.save_settings(default_settings)
        except Exception as e:
            print(f"Error resetting admin settings: {e}")
            return False
