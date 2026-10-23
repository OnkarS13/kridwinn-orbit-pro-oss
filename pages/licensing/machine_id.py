"""
Machine Fingerprinting Module
Generates unique hardware-based machine IDs for license binding
"""

import sys
import hashlib
import platform
import subprocess
from typing import Optional


def get_machine_id() -> str:
    """
    Generate a unique machine ID based on hardware characteristics.
    Uses motherboard UUID on Windows, system UUID on Linux/Mac.
    
    Returns:
        str: 16-character hexadecimal machine ID
    """
    try:
        if sys.platform == 'win32':
            return _get_windows_machine_id()
        elif sys.platform == 'darwin':
            return _get_mac_machine_id()
        else:
            return _get_linux_machine_id()
    except Exception as e:
        # Fallback: hash of hostname + platform info
        fallback = f"{platform.node()}-{platform.system()}-{platform.machine()}"
        return hashlib.sha256(fallback.encode()).hexdigest()[:16].upper()


def _get_windows_machine_id() -> str:
    """Get machine ID on Windows using WMIC for motherboard UUID"""
    try:
        # Try to get motherboard UUID
        cmd = 'wmic csproduct get uuid'
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
        
        # Parse UUID from output
        lines = output.strip().split('\n')
        if len(lines) >= 2:
            uuid = lines[1].strip()
            if uuid and uuid != '' and 'UUID' not in uuid:
                # Clean and format the UUID
                clean_uuid = uuid.replace('-', '').replace(' ', '')
                return clean_uuid[:16].upper()
        
        # Fallback: use processor ID
        cmd = 'wmic cpu get processorid'
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
        lines = output.strip().split('\n')
        if len(lines) >= 2:
            proc_id = lines[1].strip()
            if proc_id:
                return hashlib.sha256(proc_id.encode()).hexdigest()[:16].upper()
        
    except Exception:
        pass
    
    # Final fallback
    return _get_fallback_id()


def _get_mac_machine_id() -> str:
    """Get machine ID on macOS using IOPlatformUUID"""
    try:
        cmd = "ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID"
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
        
        # Extract UUID from output like: "IOPlatformUUID" = "XXXXX-XXXX-XXXX"
        if 'IOPlatformUUID' in output:
            uuid = output.split('=')[1].strip().strip('"')
            clean_uuid = uuid.replace('-', '')
            return clean_uuid[:16].upper()
    except Exception:
        pass
    
    return _get_fallback_id()


def _get_linux_machine_id() -> str:
    """Get machine ID on Linux from /etc/machine-id or /var/lib/dbus/machine-id"""
    try:
        # Try /etc/machine-id first
        try:
            with open('/etc/machine-id', 'r') as f:
                machine_id = f.read().strip()
                if machine_id:
                    return machine_id[:16].upper()
        except FileNotFoundError:
            pass
        
        # Try /var/lib/dbus/machine-id
        try:
            with open('/var/lib/dbus/machine-id', 'r') as f:
                machine_id = f.read().strip()
                if machine_id:
                    return machine_id[:16].upper()
        except FileNotFoundError:
            pass
        
        # Try DMI product UUID
        cmd = "cat /sys/class/dmi/id/product_uuid"
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
        uuid = output.strip().replace('-', '')
        if uuid:
            return uuid[:16].upper()
            
    except Exception:
        pass
    
    return _get_fallback_id()


def _get_fallback_id() -> str:
    """Generate fallback machine ID from system info"""
    components = [
        platform.node(),           # Hostname
        platform.system(),         # OS name
        platform.machine(),        # Machine type
        platform.processor(),      # Processor info
    ]
    
    combined = '-'.join(str(c) for c in components if c)
    return hashlib.sha256(combined.encode()).hexdigest()[:16].upper()


def format_machine_id(machine_id: str) -> str:
    """
    Format machine ID for display (e.g., A1B2C3D4E5F6G7H8)
    
    Args:
        machine_id: Raw machine ID string
        
    Returns:
        Formatted machine ID
    """
    # Remove any non-alphanumeric characters
    clean = ''.join(c for c in machine_id if c.isalnum())
    # Ensure uppercase and exactly 16 characters
    return clean[:16].upper().ljust(16, '0')


if __name__ == "__main__":
    # Test the machine ID generation
    machine_id = get_machine_id()
    print(f"Machine ID: {machine_id}")
    print(f"Formatted: {format_machine_id(machine_id)}")
    print(f"Platform: {platform.system()} {platform.release()}")
    print(f"Hostname: {platform.node()}")

