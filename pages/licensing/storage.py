"""
Encrypted Local Storage Module
Handles secure storage of activation data locally
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
import base64
import hashlib


class ActivationStorage:
    """Manages encrypted local storage of activation data"""
    
    def __init__(self, storage_file: str = "activation_data.enc"):
        self.storage_file = Path(storage_file)
        self.cipher = self._get_cipher()
    
    def _get_cipher(self) -> Fernet:
        """Generate Fernet cipher from the build-time activation salt"""
        from .build_secrets import get_secret
        # Derive a proper Fernet key from the salt
        key_material = hashlib.sha256(get_secret("KRIDWINN_ACTIVATION_SALT")).digest()
        # Fernet requires base64-encoded 32-byte key
        fernet_key = base64.urlsafe_b64encode(key_material)
        return Fernet(fernet_key)
    
    def save_activation_data(self, data: Dict[str, Any]) -> bool:
        """
        Save activation data to encrypted file
        
        Args:
            data: Dictionary containing activation information
            
        Returns:
            bool: True if successful
        """
        try:
            # Prepare data (convert datetime objects, etc.)
            prepared = self._prepare_data_for_storage(data)
            prepared['saved_at'] = datetime.now().isoformat()

            # Preserve stored credentials if not present in new data
            try:
                existing = self.load_activation_data()
            except Exception:
                existing = None
            if existing:
                for field in ('stored_username', 'stored_password'):
                    if field in existing and field not in prepared:
                        prepared[field] = existing[field]
            
            # Convert to JSON
            json_data = json.dumps(prepared, indent=2)
            
            # Encrypt
            encrypted = self.cipher.encrypt(json_data.encode())
            
            # Write to file
            with open(self.storage_file, 'wb') as f:
                f.write(encrypted)
            
            return True
            
        except Exception as e:
            print(f"Error saving activation data: {e}")
            return False
    
    def load_activation_data(self) -> Optional[Dict[str, Any]]:
        """
        Load and decrypt activation data from file
        
        Returns:
            Dictionary with activation data or None if not found/invalid
        """
        if not self.storage_file.exists():
            return None
        
        try:
            # Read encrypted file
            with open(self.storage_file, 'rb') as f:
                encrypted = f.read()
            
            # Decrypt
            decrypted = self.cipher.decrypt(encrypted)
            
            # Parse JSON
            data = json.loads(decrypted.decode())
            
            return data
            
        except Exception as e:
            print(f"Error loading activation data: {e}")
            # If decryption fails, file might be corrupted or tampered
            return None
    
    def delete_activation_data(self) -> bool:
        """Delete activation data file"""
        try:
            if self.storage_file.exists():
                self.storage_file.unlink()
            return True
        except Exception as e:
            print(f"Error deleting activation data: {e}")
            return False

    def _prepare_data_for_storage(self, obj: Any) -> Any:
        """Recursively convert data into JSON-serializable format"""
        if isinstance(obj, dict):
            return {k: self._prepare_data_for_storage(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._prepare_data_for_storage(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(self._prepare_data_for_storage(v) for v in obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        isoformat = getattr(obj, "isoformat", None)
        if callable(isoformat):
            try:
                return isoformat()
            except TypeError:
                pass
        return obj
    
    def is_activated(self) -> bool:
        """Check if activation data exists and is valid"""
        data = self.load_activation_data()
        if not data:
            return False
        
        # Check for required fields (supports both old license_key and new license_id)
        has_license = 'license_id' in data or 'license_key' in data
        has_required = 'machine_id' in data and 'activated_at' in data
        return has_license and has_required
    
    def get_license_key(self) -> Optional[str]:
        """Get stored license key (legacy)"""
        data = self.load_activation_data()
        return data.get('license_key') if data else None

    def get_license_id(self) -> Optional[str]:
        """Get stored license ID"""
        data = self.load_activation_data()
        return data.get('license_id') if data else None

    def get_license_data(self) -> Optional[dict]:
        """Get the full signed license data for re-verification"""
        data = self.load_activation_data()
        if not data:
            return None
        license_data = data.get('license_data')
        return license_data if license_data else None
    
    def get_machine_id(self) -> Optional[str]:
        """Get stored machine ID"""
        data = self.load_activation_data()
        return data.get('machine_id') if data else None
    
    def get_last_check_time(self) -> Optional[datetime]:
        """Get timestamp of last license check"""
        data = self.load_activation_data()
        if not data or 'last_check' not in data:
            return None
        
        try:
            return datetime.fromisoformat(data['last_check'])
        except Exception:
            return None
    
    def update_last_check_time(self) -> bool:
        """Update the last check timestamp (monotonic ratchet - only moves forward)"""
        data = self.load_activation_data()
        if not data:
            return False

        now = datetime.now()
        last_check = data.get('last_check')
        if last_check:
            try:
                last = datetime.fromisoformat(last_check)
                if now > last:
                    data['last_check'] = now.isoformat()
                # If now <= last, don't update (clock was rolled back)
            except (ValueError, TypeError):
                data['last_check'] = now.isoformat()
        else:
            data['last_check'] = now.isoformat()
        return self.save_activation_data(data)
    
    def get_activation_info(self) -> Dict[str, Any]:
        """Get complete activation information"""
        data = self.load_activation_data()
        if not data:
            return {
                'activated': False,
                'license_id': None,
                'license_key': None,
                'machine_id': None,
                'activated_at': None,
                'last_check': None,
                'expires_at': None,
                'trial_days': None
            }
        
        return {
            'activated': True,
            'license_id': data.get('license_id'),
            'license_key': data.get('license_key'),
            'machine_id': data.get('machine_id'),
            'activated_at': data.get('activated_at'),
            'last_check': data.get('last_check'),
            'expires_at': data.get('expires_at'),
            'trial_days': data.get('trial_days'),
            'status': data.get('status', 'active')
        }


class PlaintextStorage(ActivationStorage):
    """
    Non-encrypted storage for development/testing
    DO NOT USE IN PRODUCTION
    """
    
    def __init__(self, storage_file: str = "activation_data.json"):
        self.storage_file = Path(storage_file)
        # No cipher needed
    
    def save_activation_data(self, data: Dict[str, Any]) -> bool:
        try:
            prepared = self._prepare_data_for_storage(data)
            prepared['saved_at'] = datetime.now().isoformat()
            with open(self.storage_file, 'w') as f:
                json.dump(prepared, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving activation data: {e}")
            return False
    
    def load_activation_data(self) -> Optional[Dict[str, Any]]:
        if not self.storage_file.exists():
            return None
        
        try:
            with open(self.storage_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading activation data: {e}")
            return None


if __name__ == "__main__":
    # Test encryption/decryption
    print("Testing ActivationStorage...")
    
    storage = ActivationStorage("test_activation.enc")
    
    # Test data
    test_data = {
        'license_key': 'LIC-TEST-1234-5678-ABCD',
        'machine_id': 'A1B2C3D4E5F6G7H8',
        'activated_at': datetime.now().isoformat(),
        'last_check': datetime.now().isoformat(),
        'expires_at': '2025-12-31T23:59:59',
        'trial_days': 7,
        'status': 'active'
    }
    
    # Save
    print("\n1. Saving activation data...")
    success = storage.save_activation_data(test_data)
    print(f"   ✅ Saved: {success}")
    
    # Load
    print("\n2. Loading activation data...")
    loaded = storage.load_activation_data()
    print(f"   ✅ Loaded: {loaded is not None}")
    if loaded:
        print(f"   License Key: {loaded.get('license_key')}")
        print(f"   Machine ID: {loaded.get('machine_id')}")
    
    # Check activation
    print("\n3. Checking activation status...")
    is_activated = storage.is_activated()
    print(f"   ✅ Activated: {is_activated}")
    
    # Get info
    print("\n4. Getting activation info...")
    info = storage.get_activation_info()
    print(f"   Status: {info['status']}")
    print(f"   Activated: {info['activated']}")
    
    # Cleanup
    storage.delete_activation_data()
    print("\n✅ Test complete!")

