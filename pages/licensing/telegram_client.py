"""
Telegram Bot API Client
Handles communication with Telegram bot for license validation
"""

import requests
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from .firebase_client import get_firebase_client


logger = logging.getLogger(__name__)


class TelegramBotClient:
    """Client for interacting with Telegram Bot API"""
    
    def __init__(
        self,
        bot_token: str,
        firebase_creds_path: Optional[str] = None,
        firebase_creds_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize Telegram bot client
        
        Args:
            bot_token: Telegram bot token from @BotFather
            firebase_creds_path: Path to Firebase credentials JSON
        """
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.timeout = 10  # seconds
        
        # Initialize Firebase client
        self.firebase = None
        try:
            if firebase_creds_data is not None or firebase_creds_path is not None:
                self.firebase = get_firebase_client(
                    credentials_path=firebase_creds_path,
                    credentials_data=firebase_creds_data,
                )
                logger.info("Firebase client initialized for Telegram bot")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
    
    def validate_license(self, license_key: str, machine_id: str) -> Dict[str, Any]:
        """
        Validate license key and activate for this machine
        
        Args:
            license_key: License key to validate
            machine_id: Unique machine identifier
            
        Returns:
            Dictionary with validation result
        """
        try:
            # Use Firebase if available
            if self.firebase and self.firebase.is_connected():
                logger.info(f"Validating license via Firebase: {license_key[:8]}...")
                
                # Activate license in Firebase
                success, message = self.firebase.activate_license(license_key, machine_id)
                
                if success:
                    # Get license data
                    license_data = self.firebase.get_license(license_key)
                    
                    return {
                        'valid': True,
                        'message': message,
                        'data': license_data
                    }
                else:
                    return {
                        'valid': False,
                        'message': message,
                        'data': None
                    }
            else:
                # Fallback to mock mode
                logger.warning("Firebase not available, using mock validation")
                return {
                    'valid': True,
                    'message': 'License activated successfully (MOCK)',
                    'data': {
                        'license_key': license_key,
                        'machine_id': machine_id,
                        'activated_at': datetime.now().isoformat(),
                        'expires_at': '2099-12-31T23:59:59',
                        'trial_days': 365,
                        'status': 'active'
                    }
                }
            
        except Exception as e:
            logger.error(f"License validation error: {e}")
            return {
                'valid': False,
                'message': f'Validation error: {str(e)}',
                'data': None
            }
    
    def check_license_status(self, machine_id: str) -> Dict[str, Any]:
        """
        Check current license status for machine
        
        Args:
            machine_id: Unique machine identifier
            
        Returns:
            Dictionary with license status
        """
        try:
            # Use Firebase if available
            if self.firebase and self.firebase.is_connected():
                logger.info(f"Checking license status via Firebase for machine {machine_id}")
                
                # Get license by machine ID
                license_data = self.firebase.get_license_by_machine(machine_id)
                
                if not license_data:
                    return {
                        'valid': False,
                        'status': 'not_found',
                        'message': 'No license found for this machine'
                    }
                
                # Validate license
                license_key = license_data.get('license_key')
                result = self.firebase.validate_license(license_key, machine_id)
                
                return {
                    'valid': result['valid'],
                    'status': result['status'],
                    'is_blocked': license_data.get('is_blocked', False),
                    'is_expired': result['status'] == 'expired',
                    'expires_at': license_data.get('expires_at'),
                    'extended_at': license_data.get('extended_at'),  # Include extended_at to detect purchased licenses
                    'message': result['message'],
                    'revoke_reason': license_data.get('revoke_reason', '')  # Include revoke reason
                }
            else:
                # Fallback to mock mode
                logger.warning("Firebase not available, using mock status check")
                return {
                    'valid': True,
                    'status': 'active',
                    'expires_at': '2099-12-31T23:59:59',
                    'is_blocked': False,
                    'is_expired': False,
                    'message': 'License is active (MOCK)'
                }
            
        except Exception as e:
            logger.error(f"Status check error: {e}")
            return {
                'valid': False,
                'status': 'error',
                'message': f'Status check error: {str(e)}'
            }
    
    def send_notification(self, chat_id: int, message: str) -> bool:
        """
        Send notification message to admin via Telegram
        
        Args:
            chat_id: Telegram chat ID (admin's user ID)
            message: Message text to send
            
        Returns:
            bool: True if sent successfully
        """
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, json=payload, timeout=self.timeout)
            
            if response.status_code == 200:
                logger.info(f"Notification sent to {chat_id}")
                return True
            else:
                logger.error(f"Failed to send notification: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Notification error: {e}")
            return False
    
    def send_activation_notification(self, admin_id: int, activation_data: Dict[str, Any]) -> bool:
        """
        Send activation notification to master admin
        
        Args:
            admin_id: Master admin Telegram ID
            activation_data: Dictionary with activation information
            
        Returns:
            bool: True if sent successfully
        """
        try:
            machine_id = activation_data.get('machine_id', 'Unknown')
            license_key = activation_data.get('license_key', 'Unknown')
            user_name = activation_data.get('user_info', {}).get('name', 'Unknown User')
            
            message = f"""
✅ <b>NEW ACTIVATION</b>

User: {user_name}
Machine ID: <code>{machine_id}</code>
License: <code>{license_key[:8]}...{license_key[-4:]}</code>

Activated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Trial: {activation_data.get('trial_days', 'N/A')} days
Expires: {activation_data.get('expires_at', 'N/A')}

App: Kridwinn Orbit Pro
"""
            
            return self.send_notification(admin_id, message)
            
        except Exception as e:
            logger.error(f"Activation notification error: {e}")
            return False
    
    def log_check_in(self, machine_id: str) -> bool:
        """
        Log a check-in event (machine is online and checking license)
        
        Args:
            machine_id: Machine identifier
            
        Returns:
            bool: True if logged successfully
        """
        try:
            logger.info(f"Check-in logged for machine {machine_id}")
            
            # TODO: Implement actual logging via webhook to Firestore
            
            return True
            
        except Exception as e:
            logger.error(f"Check-in logging error: {e}")
            return False


class MockTelegramClient(TelegramBotClient):
    """
    Mock Telegram client for testing without actual bot
    Always returns success responses
    """
    
    def __init__(self):
        # No bot token needed for mock
        self.bot_token = "MOCK_TOKEN"
        self.base_url = "https://api.telegram.org/botMOCK"
        self.timeout = 30
    
    def validate_license(self, license_key: str, machine_id: str) -> Dict[str, Any]:
        """Mock validation - always succeeds"""
        logger.info(f"[MOCK] Validating license: {license_key} for {machine_id}")
        
        return {
            'valid': True,
            'message': 'License activated successfully (MOCK)',
            'data': {
                'license_key': license_key,
                'machine_id': machine_id,
                'activated_at': datetime.now().isoformat(),
                'expires_at': '2099-12-31T23:59:59',
                'trial_days': 365,
                'status': 'active',
                'first_activation': datetime.now().isoformat(),
                'created_by': 'mock_system',
                'user_info': {
                    'name': 'Mock User',
                    'email': 'mock@example.com'
                }
            }
        }
    
    def check_license_status(self, machine_id: str) -> Dict[str, Any]:
        """Mock status check - always active"""
        logger.info(f"[MOCK] Checking status for {machine_id}")
        
        return {
            'valid': True,
            'status': 'active',
            'expires_at': '2099-12-31T23:59:59',
            'is_blocked': False,
            'is_expired': False,
            'message': 'License is active (MOCK)'
        }
    
    def send_notification(self, chat_id: int, message: str) -> bool:
        """Mock notification - just logs"""
        logger.info(f"[MOCK] Notification to {chat_id}: {message[:50]}...")
        return True
    
    def send_activation_notification(self, admin_id: int, activation_data: Dict[str, Any]) -> bool:
        """Mock activation notification"""
        logger.info(f"[MOCK] Activation notification for {activation_data.get('machine_id')}")
        return True
    
    def log_check_in(self, machine_id: str) -> bool:
        """Mock check-in log"""
        logger.info(f"[MOCK] Check-in for {machine_id}")
        return True


if __name__ == "__main__":
    # Test mock client
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Mock Telegram Client...")
    client = MockTelegramClient()
    
    # Test validation
    print("\n1. Testing license validation...")
    result = client.validate_license("LIC-TEST-1234-5678-ABCD", "A1B2C3D4E5F6G7H8")
    print(f"   Valid: {result['valid']}")
    print(f"   Message: {result['message']}")
    
    # Test status check
    print("\n2. Testing status check...")
    status = client.check_license_status("A1B2C3D4E5F6G7H8")
    print(f"   Status: {status['status']}")
    print(f"   Valid: {status['valid']}")
    
    # Test notification
    print("\n3. Testing notification...")
    sent = client.send_notification(123456789, "Test message")
    print(f"   Sent: {sent}")
    
    print("\n✅ Mock client test complete!")

