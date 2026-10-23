"""
Utility script to encrypt sensitive configuration files.

Usage:
    python secure_config/encrypt_config.py

This will:
    - generate a new Fernet key (printed to stdout – save it!)
    - encrypt licensing_config.json -> licensing_config.enc
    - encrypt firebase_admin.json -> firebase_creds.enc

Install dependency first:
    pip install cryptography
"""

from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError as exc:
    raise SystemExit(
        "cryptography package is required. Install with 'pip install cryptography'"
    ) from exc


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "licensing_config.json"
FIREBASE_FILE = BASE_DIR / "firebase_admin.json"
CONFIG_ENC_FILE = BASE_DIR / "licensing_config.enc"
FIREBASE_ENC_FILE = BASE_DIR / "firebase_creds.enc"


def _encrypt_file(source: Path, target: Path, cipher: Fernet) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    data = source.read_bytes()
    encrypted = cipher.encrypt(data)
    target.write_bytes(encrypted)
    print(f"[encrypt_config] Encrypted {source.name} -> {target.name}")


def main() -> None:
    key = Fernet.generate_key()
    print(
        "[encrypt_config] Generated encryption key:\n"
        f"{key.decode()}\n"
        "⚠️  Save this key securely and hardcode it in the application!"
    )
    cipher = Fernet(key)

    _encrypt_file(CONFIG_FILE, CONFIG_ENC_FILE, cipher)
    _encrypt_file(FIREBASE_FILE, FIREBASE_ENC_FILE, cipher)

    print("[encrypt_config] Done. Configure the app to use the printed key.")


if __name__ == "__main__":
    main()

