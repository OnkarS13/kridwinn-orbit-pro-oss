"""
Firebase Firestore Client
Handles all database operations for licensing system
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import firebase_admin  # type: ignore
from firebase_admin import credentials, firestore  # type: ignore
from pathlib import Path

logger = logging.getLogger(__name__)


class FirebaseClient:
    """Client for Firebase Firestore operations"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern - only one Firebase instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        credentials_data: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize Firebase client
        
        Args:
            credentials_path: Path to Firebase service account JSON
            credentials_data: Dict with service account data (used if provided)
        """
        if self._initialized:
            return
        
        self.db = None
        self.credentials_path = credentials_path
        self.credentials_data = credentials_data
        
        if credentials_data:
            self._initialize_firebase(credentials_data=credentials_data)
        elif credentials_path:
            self._initialize_firebase(credentials_path)
        else:
            logger.warning("Firebase credentials not provided - client not initialized")
    
    def _initialize_firebase(
        self,
        credentials_path: Optional[str] = None,
        credentials_data: Optional[Dict[str, Any]] = None
    ):
        """Initialize Firebase Admin SDK"""
        try:
            if not firebase_admin._apps:
                if credentials_data:
                    cred = credentials.Certificate(credentials_data)
                elif credentials_path:
                    cred = credentials.Certificate(credentials_path)
                else:
                    raise ValueError("No Firebase credentials supplied")
                firebase_admin.initialize_app(cred)
                logger.info("Firebase initialized successfully")
            
            self.db = firestore.client()
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    
    def is_connected(self) -> bool:
        """Check if Firebase is connected"""
        return self.db is not None
    
    # ==================== LICENSE OPERATIONS ====================
    
    def create_license(self, license_data: Dict[str, Any]) -> bool:
        """
        Create a new license in Firestore
        
        Args:
            license_data: Dictionary with license information
            
        Returns:
            bool: True if successful
        """
        try:
            license_key = license_data.get('license_key')
            if not license_key:
                logger.error("License key is required")
                return False
            
            # Add timestamps (created_at already comes as ISO string from license_generator)
            # Only set created_at if not already present (should already be ISO format string)
            if 'created_at' not in license_data:
                license_data['created_at'] = datetime.now().isoformat()
            license_data['last_check_in'] = None
            license_data['total_launches'] = 0
            license_data['is_blocked'] = False
            
            # Save to Firestore
            self.db.collection('licenses').document(license_key).set(license_data)
            logger.info(f"License created: {license_key}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create license: {e}")
            return False
    
    def get_license(self, license_key: str) -> Optional[Dict[str, Any]]:
        """
        Get license by key
        
        Args:
            license_key: License key to retrieve
            
        Returns:
            License data or None
        """
        try:
            doc = self.db.collection('licenses').document(license_key).get()
            
            if doc.exists:
                return doc.to_dict()
            else:
                logger.warning(f"License not found: {license_key}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get license: {e}")
            return None
    
    def get_license_by_machine(self, machine_id: str) -> Optional[Dict[str, Any]]:
        """
        Get license by machine ID
        
        Args:
            machine_id: Machine ID to search for
            
        Returns:
            License data or None
        """
        try:
            # Query licenses where machine_id matches
            licenses = self.db.collection('licenses').where('machine_id', '==', machine_id).limit(1).stream()
            
            for license_doc in licenses:
                data = license_doc.to_dict()
                data['license_key'] = license_doc.id
                return data
            
            logger.warning(f"No license found for machine: {machine_id}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to get license by machine: {e}")
            return None
    
    def activate_license(self, license_key: str, machine_id: str) -> tuple[bool, str]:
        """
        Activate a license for a specific machine
        
        Args:
            license_key: License key
            machine_id: Machine ID to bind to
            
        Returns:
            Tuple of (success, message)
        """
        try:
            license_data = self.get_license(license_key)
            
            if not license_data:
                return False, "License key not found"
            
            # Check if already activated
            if license_data.get('machine_id'):
                if license_data['machine_id'] == machine_id:
                    return True, "License already activated on this machine"
                else:
                    return False, "License already activated on another machine"
            
            # Check if expired
            expires_at = license_data.get('expires_at')
            if expires_at:
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)
                # Handle timezone-aware comparison
                now = datetime.now()
                if expires_at.tzinfo:
                    # expires_at is timezone-aware, make now timezone-aware too
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                if now > expires_at:
                    return False, "License has expired"
            
            # Activate license (store first_activation as ISO format string for consistency)
            self.db.collection('licenses').document(license_key).update({
                'machine_id': machine_id,
                'first_activation': datetime.now().isoformat(),
                'status': 'active'
            })
            
            logger.info(f"License activated: {license_key} -> {machine_id}")
            return True, "License activated successfully"
            
        except Exception as e:
            logger.error(f"Failed to activate license: {e}")
            return False, f"Activation error: {str(e)}"
    
    def validate_license(self, license_key: str, machine_id: str) -> Dict[str, Any]:
        """
        Validate license and return status
        
        Args:
            license_key: License key
            machine_id: Machine ID
            
        Returns:
            Dictionary with validation result
        """
        try:
            license_data = self.get_license(license_key)
            
            if not license_data:
                return {
                    'valid': False,
                    'status': 'not_found',
                    'message': 'License key not found'
                }
            
            # Check machine binding
            if license_data.get('machine_id') != machine_id:
                return {
                    'valid': False,
                    'status': 'wrong_machine',
                    'message': 'License is bound to a different machine'
                }
            
            # Check if blocked
            if license_data.get('is_blocked'):
                return {
                    'valid': False,
                    'status': 'blocked',
                    'message': 'License has been revoked'
                }
            
            # Check expiration
            expires_at = license_data.get('expires_at')
            if expires_at:
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)
                # Handle timezone-aware comparison
                now = datetime.now()
                if expires_at.tzinfo:
                    # expires_at is timezone-aware, make now timezone-aware too
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                if now > expires_at:
                    return {
                        'valid': False,
                        'status': 'expired',
                        'message': 'License has expired'
                    }
            
            # Update check-in (store last_check_in as ISO format string for consistency)
            self.db.collection('licenses').document(license_key).update({
                'last_check_in': datetime.now().isoformat(),
                'total_launches': firestore.Increment(1)
            })
            
            return {
                'valid': True,
                'status': 'active',
                'message': 'License is valid',
                'data': license_data
            }
            
        except Exception as e:
            logger.error(f"Failed to validate license: {e}")
            return {
                'valid': False,
                'status': 'error',
                'message': f'Validation error: {str(e)}'
            }
    
    def revoke_license(self, license_key: str, reason: str = "") -> bool:
        """
        Revoke a license
        
        Args:
            license_key: License key to revoke
            reason: Reason for revocation
            
        Returns:
            bool: True if successful
        """
        try:
            # Store revoked_at as ISO format string for consistency
            self.db.collection('licenses').document(license_key).update({
                'is_blocked': True,
                'status': 'revoked',
                'revoked_at': datetime.now().isoformat(),
                'revoke_reason': reason
            })
            
            logger.info(f"License revoked: {license_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to revoke license: {e}")
            return False
    
    def restore_license(self, license_key: str) -> bool:
        """
        Restore a previously revoked license
        
        Args:
            license_key: License key to restore
        """
        try:
            doc = self.db.collection('licenses').document(license_key).get()
            if not doc.exists:
                return False
            
            data = doc.to_dict()
            # Determine status based on activation
            if data.get('machine_id'):
                new_status = 'active'
            else:
                new_status = 'pending'
            
            update_data = {
                'is_blocked': False,
                'status': new_status,
                'revoked_at': None,
                'revoke_reason': None
            }
            
            self.db.collection('licenses').document(license_key).update(update_data)
            logger.info(f"License restored: {license_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore license: {e}")
            return False
    
    def extend_license(self, license_key: str, days: int) -> bool:
        """
        Extend license expiration
        
        Args:
            license_key: License key
            days: Number of days to extend
            
        Returns:
            bool: True if successful
        """
        try:
            license_data = self.get_license(license_key)
            if not license_data:
                return False
            
            expires_at = license_data.get('expires_at')
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            elif not expires_at:
                expires_at = datetime.now()
            
            new_expiry = expires_at + timedelta(days=days)
            
            # Store as ISO format string to maintain consistency with license creation
            self.db.collection('licenses').document(license_key).update({
                'expires_at': new_expiry.isoformat(),
                'extended_at': datetime.now().isoformat(),
                'extended_days': days
            })
            
            logger.info(f"License extended: {license_key} by {days} days")
            return True
            
        except Exception as e:
            logger.error(f"Failed to extend license: {e}")
            return False
    
    def set_license_expiry(self, license_key: str, days: int) -> bool:
        """
        Set license expiration to exactly X days from now (replaces current expiry)
        
        Args:
            license_key: License key
            days: Number of days from now to set expiry
            
        Returns:
            bool: True if successful
        """
        try:
            license_data = self.get_license(license_key)
            if not license_data:
                return False
            
            # Set expiry to exactly X days from now
            new_expiry = datetime.now() + timedelta(days=days)
            
            # Handle timezone if needed
            if license_data.get('expires_at'):
                old_expires_at = license_data.get('expires_at')
                if isinstance(old_expires_at, str):
                    old_expires_at = datetime.fromisoformat(old_expires_at)
                if old_expires_at.tzinfo:
                    from datetime import timezone
                    new_expiry = datetime.now(timezone.utc) + timedelta(days=days)
            
            # Store as ISO format string to maintain consistency with license creation
            self.db.collection('licenses').document(license_key).update({
                'expires_at': new_expiry.isoformat(),
                'extended_at': datetime.now().isoformat(),
                'extended_days': days
            })
            
            logger.info(f"License expiry set: {license_key} to {days} days from now")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set license expiry: {e}")
            return False
    
    # ==================== ADMIN OPERATIONS ====================
    
    def get_admin(self, admin_id: str) -> Optional[Dict[str, Any]]:
        """Get admin by ID"""
        try:
            doc = self.db.collection('admins').document(admin_id).get()
            return doc.to_dict() if doc.exists else None
        except Exception as e:
            logger.error(f"Failed to get admin: {e}")
            return None
    
    def get_admin_by_telegram(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get admin by Telegram ID"""
        try:
            admins = self.db.collection('admins').where('telegram_id', '==', telegram_id).limit(1).stream()
            for admin_doc in admins:
                data = admin_doc.to_dict()
                data['admin_id'] = admin_doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Failed to get admin by telegram: {e}")
            return None
    
    # ==================== ASSISTANT OPERATIONS ====================
    
    def create_assistant(self, assistant_data: Dict[str, Any]) -> bool:
        """Create a new assistant"""
        try:
            assistant_id = assistant_data.get('assistant_id')
            # created_at already comes as ISO string from telegram_bot, only set if not present
            if 'created_at' not in assistant_data:
                assistant_data['created_at'] = datetime.now().isoformat()
            assistant_data['is_active'] = True
            
            self.db.collection('assistants').document(assistant_id).set(assistant_data)
            logger.info(f"Assistant created: {assistant_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to create assistant: {e}")
            return False
    
    def get_assistant_by_telegram(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get assistant by Telegram ID"""
        try:
            assistants = self.db.collection('assistants').where('telegram_id', '==', telegram_id).limit(1).stream()
            for asst_doc in assistants:
                data = asst_doc.to_dict()
                data['assistant_id'] = asst_doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Failed to get assistant: {e}")
            return None
    
    def get_assistant(self, assistant_id: str) -> Optional[Dict[str, Any]]:
        """Get assistant by ID"""
        try:
            doc = self.db.collection('assistants').document(assistant_id).get()
            if doc.exists:
                data = doc.to_dict()
                data['assistant_id'] = doc.id
                return data
            return None
        except Exception as e:
            logger.error(f"Failed to get assistant: {e}")
            return None
    
    def get_all_assistants(self) -> List[Dict[str, Any]]:
        """Get all assistants"""
        try:
            assistants = []
            docs = self.db.collection('assistants').stream()
            
            for doc in docs:
                data = doc.to_dict()
                data['assistant_id'] = doc.id
                assistants.append(data)
            
            return assistants
        except Exception as e:
            logger.error(f"Failed to get all assistants: {e}")
            return []
    
    def update_assistant(self, assistant_id: str, updates: Dict[str, Any]) -> bool:
        """Update assistant data"""
        try:
            self.db.collection('assistants').document(assistant_id).update(updates)
            logger.info(f"Assistant updated: {assistant_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update assistant: {e}")
            return False
    
    def delete_assistant(self, assistant_id: str) -> bool:
        """Delete an assistant"""
        try:
            self.db.collection('assistants').document(assistant_id).delete()
            logger.info(f"Assistant deleted: {assistant_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete assistant: {e}")
            return False
    
    # ==================== LOGGING OPERATIONS ====================
    
    def get_machine_logs(self, machine_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get activity logs for a specific machine"""
        try:
            logs = []
            docs = (self.db.collection('machine_logs')
                   .where('machine_id', '==', machine_id)
                   .order_by('timestamp', direction='DESCENDING')
                   .limit(limit)
                   .stream())
            
            for doc in docs:
                data = doc.to_dict()
                data['log_id'] = doc.id
                logs.append(data)
            
            return logs
        except Exception as e:
            logger.error(f"Failed to get machine logs: {e}")
            return []
    
    def get_tamper_attempts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get all tamper attempts"""
        try:
            attempts = []
            docs = (self.db.collection('tamper_attempts')
                   .order_by('timestamp', direction='DESCENDING')
                   .limit(limit)
                   .stream())
            
            for doc in docs:
                data = doc.to_dict()
                data['attempt_id'] = doc.id
                attempts.append(data)
            
            return attempts
        except Exception as e:
            logger.error(f"Failed to get tamper attempts: {e}")
            return []
    
    def log_machine_activity(self, machine_id: str, license_key: str, event_type: str, status: str = 'success') -> bool:
        """Log machine activity"""
        try:
            log_data = {
                'machine_id': machine_id,
                'license_key': license_key,
                'event_type': event_type,
                'status': status,
                'timestamp': datetime.now()
            }
            
            self.db.collection('machine_logs').add(log_data)
            return True
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
            return False
    
    def log_tamper_attempt(self, machine_id: str, license_key: str, tamper_type: str, details: str) -> bool:
        """Log a tamper attempt"""
        try:
            tamper_data = {
                'machine_id': machine_id,
                'license_key': license_key,
                'tamper_type': tamper_type,
                'details': details,
                'timestamp': datetime.now(),
                'action_taken': 'logged'
            }
            
            self.db.collection('tamper_attempts').add(tamper_data)
            logger.warning(f"Tamper attempt logged: {tamper_type} on {machine_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to log tamper attempt: {e}")
            return False
    
    # ==================== QUERY OPERATIONS ====================
    
    def get_licenses_by_creator(self, creator_id: str) -> List[Dict[str, Any]]:
        """Get all licenses created by a specific user"""
        try:
            licenses = []
            docs = self.db.collection('licenses').where('created_by', '==', creator_id).stream()
            
            for doc in docs:
                data = doc.to_dict()
                data['license_key'] = doc.id
                licenses.append(data)
            
            return licenses
        except Exception as e:
            logger.error(f"Failed to get licenses by creator: {e}")
            return []
    
    def get_all_licenses(self) -> List[Dict[str, Any]]:
        """Get all licenses (master admin only)"""
        try:
            licenses = []
            docs = self.db.collection('licenses').stream()
            
            for doc in docs:
                data = doc.to_dict()
                data['license_key'] = doc.id
                licenses.append(data)
            
            return licenses
        except Exception as e:
            logger.error(f"Failed to get all licenses: {e}")
            return []
    
    # ==================== LOGGING OPERATIONS ====================
    
    def log_machine_event(self, log_data: Dict[str, Any]) -> bool:
        """Log a machine event"""
        try:
            log_data['timestamp'] = datetime.now()
            self.db.collection('machine_logs').add(log_data)
            return True
        except Exception as e:
            logger.error(f"Failed to log machine event: {e}")
            return False
    
    def log_tamper_attempt(self, tamper_data: Dict[str, Any]) -> bool:
        """Log a tamper attempt"""
        try:
            tamper_data['timestamp'] = datetime.now()
            self.db.collection('tamper_attempts').add(tamper_data)
            logger.warning(f"Tamper attempt logged: {tamper_data}")
            return True
        except Exception as e:
            logger.error(f"Failed to log tamper attempt: {e}")
            return False


# Global instance
_firebase_client = None

def get_firebase_client(
    credentials_path: Optional[str] = None,
    credentials_data: Optional[Dict[str, Any]] = None
) -> FirebaseClient:
    """Get global Firebase client instance"""
    global _firebase_client
    if _firebase_client is None:
        _firebase_client = FirebaseClient(credentials_path, credentials_data)
    return _firebase_client


if __name__ == "__main__":
    # Test Firebase connection
    logging.basicConfig(level=logging.INFO)
    
    import os
    creds_path = os.environ.get("FIREBASE_CREDENTIALS_PATH", "firebase_admin.json")
    
    client = FirebaseClient(creds_path)
    
    if client.is_connected():
        print("✅ Firebase connected successfully!")
        
        # Test getting admin
        admin = client.get_admin_by_telegram(int(os.environ.get("TELEGRAM_MASTER_ADMIN_ID", "0")))
        if admin:
            print(f"✅ Admin found: {admin['name']}")
    else:
        print("❌ Firebase connection failed")

