"""
Secure configuration loader.
Firebase credentials needed for one-time license registration.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    Fernet = None
    _FERNET_AVAILABLE = False


def get_base_path() -> Path:
    """Get correct base path for bundled files."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent.parent


SECURE_DIR = get_base_path() / "secure_config"
ENCRYPTED_CONFIG = SECURE_DIR / "licensing_config.enc"
ENCRYPTED_FIREBASE = SECURE_DIR / "firebase_creds.enc"



def _load_encrypted_json(path: Path) -> Dict[str, Any]:
    """Load and decrypt a JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Encrypted config missing: {path}")

    if not _FERNET_AVAILABLE:
        raise RuntimeError("Cannot decrypt config: cryptography not available")

    from .build_secrets import get_secret
    cipher = Fernet(get_secret("KRIDWINN_CONFIG_KEY"))
    encrypted = path.read_bytes()
    decrypted = cipher.decrypt(encrypted)
    return json.loads(decrypted.decode("utf-8"))


def load_licensing_config_data() -> Dict[str, Any]:
    """Load licensing config from encrypted file."""
    return _load_encrypted_json(ENCRYPTED_CONFIG)


def load_firebase_credentials_data() -> Dict[str, Any]:
    """Load Firebase credentials from encrypted file (needed for one-time registration)."""
    return _load_encrypted_json(ENCRYPTED_FIREBASE)
