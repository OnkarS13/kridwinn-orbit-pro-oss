#!/usr/bin/env python3
"""
Kridwinn Orbit Pro - Offline License Generator Tool

Usage:
    python license_tool.py generate-keys [--output-dir DIR]
    python license_tool.py create --name NAME --machine MACHINE_ID --password PASSWORD [--days N | --permanent] [--key-file PATH] [--output PATH]
    python license_tool.py verify LICENSE_FILE [--key-file PATH]
    python license_tool.py show-machine-id
"""

import argparse
import json
import sys
import os
import uuid
import base64
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding


def _canonicalize(data: dict) -> bytes:
    """Canonical JSON serialization - MUST match rsa_verifier.py"""
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')


def cmd_generate_keys(args):
    """Generate RSA 2048-bit key pair"""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    private_key_path = output_dir / "private_key.pem"
    public_key_path = output_dir / "public_key.pem"

    if private_key_path.exists():
        confirm = input(f"'{private_key_path}' already exists. Overwrite? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return

    # Generate key pair
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Save private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(private_key_path, 'wb') as f:
        f.write(private_pem)

    # Save public key
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(public_key_path, 'wb') as f:
        f.write(public_pem)

    print(f"Keys generated successfully!")
    print(f"  Private key: {private_key_path}")
    print(f"  Public key:  {public_key_path}")
    print()
    print("IMPORTANT:")
    print("  1. Keep private_key.pem SECRET - never share it")
    print("  2. Copy the public key below into rsa_verifier.py EMBEDDED_PUBLIC_KEY:")
    print()
    print(public_pem.decode())


def cmd_create(args):
    """Create a signed .lic license file"""
    # Load private key
    key_file = Path(args.key_file)
    if not key_file.exists():
        print(f"Error: Private key not found at '{key_file}'")
        print("Run 'generate-keys' first to create a key pair.")
        sys.exit(1)

    with open(key_file, 'rb') as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    # Determine license type and expiry
    if args.permanent:
        license_type = "permanent"
        expires_at = None
    else:
        license_type = "trial"
        days = args.days or 30
        expires_at = (datetime.now() + timedelta(days=days)).isoformat()

    # Build license data
    data = {
        "license_id": str(uuid.uuid4()),
        "machine_id": args.machine.upper(),
        "user_name": args.name,
        "password_hash": hashlib.sha256(args.password.encode()).hexdigest(),
        "license_type": license_type,
        "expires_at": expires_at,
        "issued_at": datetime.now().isoformat(),
    }

    # Sign
    canonical = _canonicalize(data)
    signature = private_key.sign(
        canonical,
        padding.PKCS1v15(),
        hashes.SHA256()
    )

    license_dict = {
        "data": data,
        "signature": base64.b64encode(signature).decode('ascii'),
    }

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        safe_name = args.name.lower().replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')
        output_path = Path(f"{safe_name}_{args.machine[:8].upper()}.lic")

    # Write file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(license_dict, f, indent=2)

    print(f"License created successfully!")
    print(f"  File:         {output_path}")
    print(f"  User:         {args.name}")
    print(f"  Machine ID:   {args.machine.upper()}")
    print(f"  Type:         {license_type}")
    if expires_at:
        print(f"  Expires:      {expires_at}")
    else:
        print(f"  Expires:      Never (permanent)")
    print(f"  License ID:   {data['license_id']}")
    print()
    print(f"Send this file and the password to the user.")
    print(f"  Password: {args.password}")


def cmd_verify(args):
    """Verify a .lic license file"""
    lic_path = Path(args.license_file)
    if not lic_path.exists():
        print(f"Error: License file not found at '{lic_path}'")
        sys.exit(1)

    # Load license
    with open(lic_path, 'r', encoding='utf-8') as f:
        license_dict = json.load(f)

    if "data" not in license_dict or "signature" not in license_dict:
        print("Error: Invalid license file format (missing 'data' or 'signature')")
        sys.exit(1)

    # Load public key
    key_file = Path(args.key_file)
    if not key_file.exists():
        print(f"Error: Public key not found at '{key_file}'")
        sys.exit(1)

    with open(key_file, 'rb') as f:
        public_key = serialization.load_pem_public_key(f.read())

    # Verify signature
    data = license_dict["data"]
    signature = base64.b64decode(license_dict["signature"])
    canonical = _canonicalize(data)

    try:
        public_key.verify(signature, canonical, padding.PKCS1v15(), hashes.SHA256())
        sig_valid = True
    except Exception:
        sig_valid = False

    print(f"License File: {lic_path}")
    print(f"  Signature:    {'VALID' if sig_valid else 'INVALID'}")
    print(f"  License ID:   {data.get('license_id', 'N/A')}")
    print(f"  User:         {data.get('user_name', 'N/A')}")
    print(f"  Machine ID:   {data.get('machine_id', 'N/A')}")
    print(f"  Type:         {data.get('license_type', 'N/A')}")
    print(f"  Issued:       {data.get('issued_at', 'N/A')}")

    expires = data.get('expires_at')
    if expires:
        try:
            exp_dt = datetime.fromisoformat(expires)
            remaining = (exp_dt - datetime.now()).days
            status = f"{expires} ({remaining} days remaining)" if remaining >= 0 else f"{expires} (EXPIRED)"
        except ValueError:
            status = expires
        print(f"  Expires:      {status}")
    else:
        print(f"  Expires:      Never (permanent)")

    if not sig_valid:
        print()
        print("WARNING: This license file has been tampered with or was not signed with the matching private key!")
        sys.exit(1)


def cmd_show_machine_id(args):
    """Display the current machine's ID"""
    # Try to import from the project
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from pages.licensing.machine_id import get_machine_id, format_machine_id
        machine_id = get_machine_id()
        formatted = format_machine_id(machine_id)
        print(f"Machine ID: {formatted}")
    except ImportError:
        # Fallback: inline implementation
        import platform
        import subprocess
        try:
            if sys.platform == 'win32':
                cmd = 'wmic csproduct get uuid'
                output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()
                lines = output.strip().split('\n')
                if len(lines) >= 2:
                    raw = lines[1].strip().replace('-', '').replace(' ', '')
                    print(f"Machine ID: {raw[:16].upper()}")
                    return
            print(f"Machine ID: (could not determine, import machine_id module)")
        except Exception as e:
            print(f"Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Kridwinn Orbit Pro - License Generator Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # generate-keys
    gen_parser = subparsers.add_parser("generate-keys", help="Generate RSA key pair")
    gen_parser.add_argument("--output-dir", default=".", help="Output directory (default: current)")

    # create
    create_parser = subparsers.add_parser("create", help="Create a signed license file")
    create_parser.add_argument("--name", required=True, help="User's name")
    create_parser.add_argument("--machine", required=True, help="Target machine ID (16 hex chars)")
    create_parser.add_argument("--password", required=True, help="Login password for the user")
    expiry_group = create_parser.add_mutually_exclusive_group()
    expiry_group.add_argument("--days", type=int, help="Trial duration in days (default: 30)")
    expiry_group.add_argument("--permanent", action="store_true", help="Create a permanent license")
    create_parser.add_argument("--key-file", default="private_key.pem", help="Path to private key (default: private_key.pem)")
    create_parser.add_argument("--output", help="Output .lic file path (default: auto-generated)")

    # verify
    verify_parser = subparsers.add_parser("verify", help="Verify a license file")
    verify_parser.add_argument("license_file", help="Path to the .lic file")
    verify_parser.add_argument("--key-file", default="public_key.pem", help="Path to public key (default: public_key.pem)")

    # show-machine-id
    subparsers.add_parser("show-machine-id", help="Display this machine's ID")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "generate-keys": cmd_generate_keys,
        "create": cmd_create,
        "verify": cmd_verify,
        "show-machine-id": cmd_show_machine_id,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
