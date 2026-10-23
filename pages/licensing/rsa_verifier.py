"""
RSA License Verification Module
Verifies digitally signed license files (.lic) for offline licensing.
"""

import json
import base64
from datetime import datetime
from typing import Tuple, Optional, Dict, Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


# ============================================================
# EMBEDDED PUBLIC KEY
# Replace this with your actual public key after running:
#   python tools/license_tool.py generate-keys
# ============================================================
EMBEDDED_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAw0IKwy/Uvq5AQ3xIz4cL
Ck9A+odocFt9WfTSA2JuBA4vtrphlJ/v9tHv3Fz2teuCek8OKMVml7WRLW2PvarR
LjnWp8UbS3hIQL+OBt1SPQM9xq+GpZsNlIr0Db3h0qLYnkqH0bmQ6KRuxNPXMcxG
mviaEFaPmg3RNZ01ZJEDSBzqVCB51ZcUQOav3MtttP7lVSuPOZzLnHm/PHi1503J
qXdx7Gak3+xcW2PDdnETrNlYh4GpTCqGkUYxVGzr1o7FXVo3/uR4ZF2x7Lq9hGsf
m3YP6M3YALL0wUz5PBP287tSHLHZvJWqS3M4Aup2bWFzzBLC8zI2vbt+pEEQ33aB
ewIDAQAB
-----END PUBLIC KEY-----"""


def _canonicalize(data: dict) -> bytes:
    """
    Convert license data dict to canonical JSON bytes.
    This MUST match the serialization used in license_tool.py.
    """
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')


def verify_license_signature(license_dict: dict) -> bool:
    """
    Verify the RSA signature of a license file.

    Args:
        license_dict: Parsed .lic file with 'data' and 'signature' keys

    Returns:
        True if signature is valid
    """
    try:
        data = license_dict["data"]
        signature = base64.b64decode(license_dict["signature"])
        canonical = _canonicalize(data)

        public_key = serialization.load_pem_public_key(EMBEDDED_PUBLIC_KEY.encode())
        public_key.verify(
            signature,
            canonical,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception:
        return False


def load_license_file(file_path: str) -> Optional[dict]:
    """
    Read and parse a .lic license file.

    Args:
        file_path: Path to the .lic file

    Returns:
        Parsed license dict or None if invalid
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            license_dict = json.load(f)

        if "data" not in license_dict or "signature" not in license_dict:
            return None

        required_fields = [
            "license_id", "machine_id", "user_name",
            "password_hash", "license_type", "issued_at"
        ]
        for field in required_fields:
            if field not in license_dict["data"]:
                return None

        return license_dict
    except Exception:
        return None


def validate_license(license_dict: dict, current_machine_id: str) -> Tuple[bool, str]:
    """
    Full offline license validation chain:
    1. Verify RSA signature (anti-forgery)
    2. Check machine ID matches (anti-sharing)
    3. Check expiry date (trial enforcement)

    Args:
        license_dict: Parsed .lic file
        current_machine_id: This machine's hardware ID

    Returns:
        (valid, message) tuple
    """
    # 1. Verify signature
    if not verify_license_signature(license_dict):
        return False, "Invalid license file. The signature verification failed."

    data = license_dict["data"]

    # 2. Check machine binding
    if data["machine_id"].upper() != current_machine_id.upper():
        return False, (
            f"This license is not valid for this machine.\n"
            f"License is for: {data['machine_id']}\n"
            f"This machine:   {current_machine_id}"
        )

    # 3. Check expiry (only for trial licenses)
    if data["license_type"] == "trial":
        expires_at = data.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at)
                if datetime.now() > expiry:
                    return False, (
                        f"This trial license has expired.\n"
                        f"Expired on: {expiry.strftime('%Y-%m-%d %H:%M')}\n"
                        "Please contact the administrator for a new license."
                    )
            except (ValueError, TypeError):
                return False, "Invalid expiry date in license file."

    return True, "License is valid."


def get_license_display_info(license_dict: dict) -> Dict[str, Any]:
    """
    Extract display-friendly info from a license dict.

    Args:
        license_dict: Parsed .lic file

    Returns:
        Dict with formatted license information
    """
    data = license_dict["data"]

    info = {
        "license_id": data.get("license_id", "Unknown"),
        "user_name": data.get("user_name", "Unknown"),
        "machine_id": data.get("machine_id", "Unknown"),
        "license_type": data.get("license_type", "Unknown"),
        "issued_at": data.get("issued_at", "Unknown"),
        "is_permanent": data.get("license_type") == "permanent",
    }

    if data.get("license_type") == "trial" and data.get("expires_at"):
        try:
            expiry = datetime.fromisoformat(data["expires_at"])
            remaining = (expiry - datetime.now()).days
            info["expires_at"] = data["expires_at"]
            info["days_remaining"] = max(0, remaining)
        except (ValueError, TypeError):
            info["expires_at"] = "Unknown"
            info["days_remaining"] = 0
    else:
        info["expires_at"] = None
        info["days_remaining"] = None

    return info
