"""
Kridwinn Orbit Pro - Offline Licensing System

RSA-signed license file verification with:
- Machine fingerprinting
- Encrypted local storage
- Trial management
"""

from .machine_id import get_machine_id
from .license_client import LicenseClient
from .activation_dialog import ActivationDialog
from .credentials import CredentialStorage

__all__ = ['get_machine_id', 'LicenseClient', 'ActivationDialog', 'CredentialStorage']
