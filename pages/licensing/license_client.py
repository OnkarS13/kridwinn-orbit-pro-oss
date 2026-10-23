"""
License Client Module
Offline license management using RSA-signed license files.
First-time activation requires internet to register with Firebase.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from .machine_id import get_machine_id, format_machine_id
from .storage import ActivationStorage
from .rsa_verifier import load_license_file, validate_license, verify_license_signature


logger = logging.getLogger(__name__)


def _load_firebase_client():
    """
    Lazily initialize Firebase client for one-time registration.
    Returns FirebaseClient instance or None if unavailable.
    """
    try:
        from .firebase_client import FirebaseClient
        from .secure_loader import load_firebase_credentials_data
        creds_data = load_firebase_credentials_data()
        client = FirebaseClient(credentials_data=creds_data)
        if client.is_connected():
            return client
    except Exception as e:
        logger.warning(f"Firebase not available: {e}")
    return None


def _register_license_online(firebase, license_id: str, machine_id: str) -> Tuple[bool, str, Optional[datetime]]:
    """
    One-time Firebase registration: bind license_id to machine_id.
    Uses atomic create() to prevent race conditions.

    Returns:
        (success, message, server_time or None)
    """
    try:
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP
        from google.api_core.exceptions import AlreadyExists

        doc_ref = firebase.db.collection("license_registrations").document(license_id)
        now = datetime.now().isoformat()

        # Atomic create - fails if document already exists (prevents TOCTOU race)
        try:
            doc_ref.create({
                "license_id": license_id,
                "machine_id": machine_id.upper(),
                "registered_at": now,
                "server_timestamp": SERVER_TIMESTAMP,
            })
            # Read back to get the resolved server timestamp
            doc = doc_ref.get()
            server_time = None
            if doc.exists:
                data = doc.to_dict()
                st = data.get("server_timestamp")
                if st:
                    server_time = st if isinstance(st, datetime) else None
            logger.info(f"License {license_id[:8]}... registered to machine {machine_id}")
            return True, "License registered successfully.", server_time

        except AlreadyExists:
            # Document already exists - check if same machine (re-activation)
            doc = doc_ref.get()
            if not doc.exists:
                return False, "Registration conflict. Please try again.", None
            data = doc.to_dict()
            registered_machine = data.get("machine_id", "")
            if registered_machine.upper() == machine_id.upper():
                logger.info(f"License {license_id[:8]}... already registered to this machine")
                server_time = data.get("server_timestamp")
                if server_time and not isinstance(server_time, datetime):
                    server_time = None
                return True, "License already registered to this machine.", server_time
            else:
                logger.warning(f"License {license_id[:8]}... already registered to machine {registered_machine}")
                return False, (
                    "This license is already activated on another device.\n\n"
                    "Each license can only be used on one device.\n"
                    "Please contact your administrator for a new license."
                ), None

    except ImportError:
        # Fallback if google.api_core not available - use transaction
        try:
            doc_ref = firebase.db.collection("license_registrations").document(license_id)

            @firebase.db.transaction
            def register_in_transaction(transaction):
                doc = doc_ref.get(transaction=transaction)
                if doc.exists:
                    data = doc.to_dict()
                    registered_machine = data.get("machine_id", "")
                    if registered_machine.upper() == machine_id.upper():
                        return True, "License already registered to this machine.", None
                    else:
                        return False, (
                            "This license is already activated on another device.\n\n"
                            "Each license can only be used on one device.\n"
                            "Please contact your administrator for a new license."
                        ), None
                else:
                    transaction.set(doc_ref, {
                        "license_id": license_id,
                        "machine_id": machine_id.upper(),
                        "registered_at": datetime.now().isoformat(),
                    })
                    return True, "License registered successfully.", None

            transaction = firebase.db.transaction()
            return register_in_transaction(transaction)
        except Exception as e:
            logger.error(f"Firebase registration error: {e}")
            return False, f"Failed to verify license online: {str(e)}", None

    except Exception as e:
        logger.error(f"Firebase registration error: {e}")
        return False, f"Failed to verify license online: {str(e)}", None


class LicenseClient:
    """
    Licensing client.
    First activation requires internet (Firebase registration).
    All subsequent logins are fully offline.
    """

    def __init__(self):
        self.storage = ActivationStorage()
        self.machine_id = format_machine_id(get_machine_id())

    def is_activated(self) -> bool:
        """Check if application is activated"""
        return self.storage.is_activated()

    def get_machine_id(self) -> str:
        """Get this machine's unique ID"""
        return self.machine_id

    def import_license_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Import and activate a .lic license file.
        Requires internet for first-time Firebase registration.

        Args:
            file_path: Path to the .lic file

        Returns:
            Tuple of (success, message)
        """
        try:
            logger.info(f"Importing license from: {file_path}")

            # 1. Load and parse .lic file
            license_dict = load_license_file(file_path)
            if license_dict is None:
                return False, "Invalid license file. Could not parse the file."

            data = license_dict["data"]

            # 2. Check if already activated with a different license
            if self.is_activated():
                existing_id = self.storage.get_license_id()
                if existing_id and existing_id != data.get("license_id"):
                    return False, "This machine is already activated with a different license."

            # 3. Offline validation: signature + machine + expiry
            valid, message = validate_license(license_dict, self.machine_id)
            if not valid:
                logger.warning(f"License validation failed: {message}")
                return False, message

            # 4. One-time Firebase registration (requires internet)
            firebase = _load_firebase_client()
            if firebase is None:
                return False, (
                    "Internet connection required for first-time activation.\n\n"
                    "Please check your internet connection and try again."
                )

            reg_success, reg_message, server_time = _register_license_online(
                firebase, data["license_id"], self.machine_id
            )
            if not reg_success:
                return False, reg_message

            # 5. Store activation data locally
            activated_at = datetime.now()
            activation_data = {
                "license_id": data["license_id"],
                "machine_id": self.machine_id,
                "user_name": data["user_name"],
                "license_type": data["license_type"],
                "expires_at": data.get("expires_at"),
                "issued_at": data["issued_at"],
                "activated_at": activated_at.isoformat(),
                "last_check": activated_at.isoformat(),
                # Store server timestamp for anti-clock-rollback protection
                "server_activated_at": server_time.isoformat() if server_time else activated_at.isoformat(),
                "local_at_activation": activated_at.isoformat(),
                # Store the full signed license for re-verification on every launch
                "license_data": license_dict,
                # Store credentials from license file
                "stored_username": data["user_name"],
                "stored_password": data["password_hash"],
                "username": data["user_name"],
            }

            if not self.storage.save_activation_data(activation_data):
                return False, "Failed to save activation data."

            logger.info("License activated successfully")
            return True, "License activated successfully!"

        except Exception as e:
            logger.error(f"Import error: {e}")
            return False, f"Failed to import license: {str(e)}"

    def check_license(self) -> Tuple[bool, str]:
        """
        Verify stored license is still valid (fully offline).
        Re-verifies the RSA signature, machine binding, and expiry.
        Uses elapsed-time approach to prevent clock rollback bypass.

        Returns:
            Tuple of (valid, message)
        """
        try:
            if not self.is_activated():
                return False, "Not activated"

            activation_data = self.storage.load_activation_data()
            if not activation_data:
                return False, "Activation data corrupted. Please re-import your license file."

            # Load stored signed license data
            license_data = self.storage.get_license_data()
            if not license_data:
                return False, "Activation data corrupted. Please re-import your license file."

            # Re-verify RSA signature + machine binding
            valid, message = validate_license(license_data, self.machine_id)
            if not valid:
                return False, message

            # Anti-clock-rollback: check expiry using elapsed time from activation
            expires_at = activation_data.get("expires_at")
            if expires_at:
                try:
                    expiry = datetime.fromisoformat(expires_at)
                    now = datetime.now()

                    # Primary check: direct expiry comparison
                    if now >= expiry:
                        return False, "License has expired."

                    # Secondary check: detect clock rollback
                    # If current time is before the last recorded check time,
                    # the clock was rolled back
                    last_check = activation_data.get("last_check")
                    if last_check:
                        last_check_time = datetime.fromisoformat(last_check)
                        if now < last_check_time:
                            logger.warning("Clock rollback detected: current time is before last check time")
                            return False, (
                                "System clock tampering detected.\n"
                                "Please set your system clock to the correct time and try again."
                            )

                    # Tertiary check: elapsed time from server-verified activation
                    server_activated_at = activation_data.get("server_activated_at")
                    local_at_activation = activation_data.get("local_at_activation")
                    if server_activated_at and local_at_activation:
                        server_time = datetime.fromisoformat(server_activated_at)
                        local_time = datetime.fromisoformat(local_at_activation)
                        # Firestore returns a timezone-aware (UTC) timestamp while all
                        # other dates here are naive local times; normalise to naive local
                        # so the comparison with `expiry` doesn't raise TypeError.
                        if server_time.tzinfo is not None:
                            server_time = server_time.astimezone().replace(tzinfo=None)
                        # Elapsed time since activation (based on local clock)
                        elapsed = now - local_time
                        # Estimated current server time
                        estimated_server_now = server_time + elapsed
                        if estimated_server_now >= expiry:
                            return False, "License has expired."

                except (ValueError, TypeError) as e:
                    logger.error(f"Error parsing expiry dates: {e}")
                    return False, "License data corrupted."

            # Update last check time (monotonic ratchet - only moves forward)
            self.storage.update_last_check_time()
            return True, "License is valid."

        except Exception as e:
            logger.error(f"License check error: {e}")
            return False, f"License check error: {str(e)}"

    def get_license_info(self) -> Dict[str, Any]:
        """Get current license information"""
        if not self.is_activated():
            return {
                "activated": False,
                "machine_id": self.machine_id,
                "license_id": None,
                "status": "not_activated",
            }

        info = self.storage.get_activation_info()
        info["machine_id"] = self.machine_id
        return info

    def get_trial_info(self) -> Optional[Dict[str, Any]]:
        """
        Get trial information.

        Returns:
            Dict with days_remaining, expires_at, is_trial, or None
        """
        if not self.is_activated():
            return None

        activation_data = self.storage.load_activation_data()
        if not activation_data:
            return None

        license_type = activation_data.get("license_type", "trial")
        is_trial = license_type == "trial"

        expires_at = activation_data.get("expires_at")
        if not expires_at:
            return {
                "days_remaining": None,
                "expires_at": None,
                "expires_at_str": "Never",
                "is_trial": False,
            }

        try:
            expiry = datetime.fromisoformat(expires_at)
        except (ValueError, TypeError):
            return None

        days_remaining = (expiry - datetime.now()).days

        return {
            "days_remaining": max(0, days_remaining),
            "expires_at": expiry,
            "expires_at_str": expiry.strftime("%Y-%m-%d"),
            "is_trial": is_trial,
        }

    def deactivate(self) -> bool:
        """Deactivate license (remove activation data)"""
        try:
            return self.storage.delete_activation_data()
        except Exception as e:
            logger.error(f"Deactivation error: {e}")
            return False
