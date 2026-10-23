"""
Path Helper for Nuitka Onefile Builds
Detects the actual EXE location (not temp extraction folder)
"""

import sys
import os
from pathlib import Path


def get_app_root() -> Path:
    """
    Get the application root directory.
    
    For onefile EXE: Returns the directory where the EXE is actually located
    For script: Returns the project root directory
    
    Returns:
        Path object pointing to the application root
    """
    if getattr(sys, 'frozen', False):
        # Running as EXE (Nuitka/PyInstaller)
        exe_dir = Path(sys.executable).parent
        
        # Check if this is a onefile build (temp folder pattern)
        is_onefile = 'onefile' in str(exe_dir).lower() or 'temp' in str(exe_dir).lower()
        
        if is_onefile:
            # For onefile builds, we need to find the real EXE location
            
            # Method 1: Check Windows Registry (set by Inno Setup installer)
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Kridwinn Orbit Pro")
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                if install_path and Path(install_path).exists():
                    return Path(install_path)
            except:
                pass
            
            # Method 2: Check for NUITKA_ONEFILE_PARENT environment variable (if set by wrapper)
            parent_dir = os.environ.get('NUITKA_ONEFILE_PARENT')
            if parent_dir and Path(parent_dir).exists():
                return Path(parent_dir)
            
            # Method 3: Use the original command line argument (before extraction)
            # sys.argv[0] contains the original EXE path before extraction
            original_exe = Path(sys.argv[0])
            if original_exe.exists() and original_exe.is_file():
                return original_exe.parent
            
            # Method 4: Check common installation directories
            # For installed apps, check %LOCALAPPDATA%\Kridwinn Orbit Pro
            local_appdata = Path(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')))
            installed_dir = local_appdata / "Kridwinn Orbit Pro"
            if installed_dir.exists():
                return installed_dir
            
            # Fallback: Use AppData for data storage
            # This ensures data persists even if we can't find the EXE location
            app_data_dir = local_appdata / "Kridwinn Orbit Pro"
            app_data_dir.mkdir(parents=True, exist_ok=True)
            return app_data_dir
        else:
            # Regular build: Use EXE directory
            return exe_dir
    else:
        # Running as script - use project root
        # Navigate up from this file's location to find app.py
        current_file = Path(__file__).resolve()
        # This file is in pages/multi_server_print/shared/
        return current_file.parent.parent.parent.parent


if __name__ == "__main__":
    # Test the function
    app_root = get_app_root()
    print(f"Application root: {app_root}")
    print(f"Frozen: {getattr(sys, 'frozen', False)}")
    print(f"sys.executable: {sys.executable}")
    print(f"sys.argv[0]: {sys.argv[0]}")
