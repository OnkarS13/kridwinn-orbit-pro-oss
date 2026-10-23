"""
Anti-Tampering Module
Detects code modifications, debugger attachment, and integrity violations.
Fully offline - no external logging.
"""

import os
import sys
import hashlib
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class AntiTamper:
    """Anti-tampering protection system"""

    def __init__(self):
        self.critical_files = []

    def calculate_file_checksum(self, file_path: str) -> Optional[str]:
        """Calculate SHA256 checksum of a file"""
        try:
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate checksum for {file_path}: {e}")
            return None

    def register_critical_files(self, file_paths: list):
        """Register critical files to monitor for integrity"""
        for file_path in file_paths:
            if os.path.exists(file_path):
                checksum = self.calculate_file_checksum(file_path)
                if checksum:
                    self.critical_files.append({
                        'path': file_path,
                        'checksum': checksum,
                    })

    def verify_all_critical_files(self) -> Tuple[bool, list]:
        """Verify all registered critical files"""
        violated = []
        for info in self.critical_files:
            current = self.calculate_file_checksum(info['path'])
            if current != info['checksum']:
                violated.append(info['path'])
        return len(violated) == 0, violated

    def is_debugger_present(self) -> bool:
        """Detect if debugger is attached"""
        if sys.gettrace() is not None:
            return True
        if sys.platform == 'win32':
            try:
                import ctypes
                if ctypes.windll.kernel32.IsDebuggerPresent():
                    return True
            except Exception:
                pass
        return False

    def check_suspicious_processes(self) -> list:
        """Check for suspicious debugging/analysis tools"""
        suspicious_names = [
            'ida.exe', 'ida64.exe', 'ollydbg.exe',
            'x64dbg.exe', 'x32dbg.exe', 'cheatengine.exe',
        ]
        found = []
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                try:
                    name = proc.info['name'].lower()
                    if name in suspicious_names:
                        found.append(name)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except ImportError:
            pass
        return found

    def run_full_check(self, machine_id: str = None, license_key: str = None) -> Tuple[bool, list]:
        """Run all anti-tamper checks"""
        issues = []

        if self.critical_files:
            valid, violated = self.verify_all_critical_files()
            if not valid:
                issues.append(f"File integrity violation: {', '.join(violated)}")

        if self.is_debugger_present():
            issues.append("Debugger detected")

        suspicious = self.check_suspicious_processes()
        if suspicious:
            issues.append(f"Suspicious processes: {', '.join(suspicious)}")

        return len(issues) == 0, issues


def create_anti_tamper(critical_files: list = None) -> AntiTamper:
    """Create and initialize anti-tamper system"""
    at = AntiTamper()
    if critical_files:
        at.register_critical_files(critical_files)
    return at
