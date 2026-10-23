"""
Credentials Generation and Management
Handles username/password generation and secure storage
"""

import secrets
import string
import hashlib
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def generate_username(name: str) -> str:
    """
    Generate username from name with random suffix
    
    Args:
        name: User's name
        
    Returns:
        Username in format: name_xxxx (e.g., john_doe_a7f3)
    """
    # Clean name: lowercase, replace spaces with underscore, remove special chars
    clean_name = name.lower().strip()
    clean_name = ''.join(c if c.isalnum() or c == ' ' else '' for c in clean_name)
    clean_name = clean_name.replace(' ', '_')
    
    # Limit length
    if len(clean_name) > 20:
        clean_name = clean_name[:20]
    
    # Generate random suffix (4 chars: letters + numbers)
    suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4))
    
    username = f"{clean_name}_{suffix}"
    return username


def generate_strong_password(length: int = 16) -> str:
    """
    Generate a strong random password
    
    Args:
        length: Password length (default 16)
        
    Returns:
        Strong password with mixed case, numbers, and symbols
    """
    # Character sets
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*()-_=+[]{}|;:,.<>?"
    
    # Ensure at least one of each type
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(symbols)
    ]
    
    # Fill the rest randomly
    all_chars = lowercase + uppercase + digits + symbols
    password.extend(secrets.choice(all_chars) for _ in range(length - 4))
    
    # Shuffle to avoid predictable pattern
    password_list = list(password)
    secrets.SystemRandom().shuffle(password_list)
    
    return ''.join(password_list)


def hash_password(password: str) -> str:
    """
    Hash password using SHA256
    
    Args:
        password: Plain text password
        
    Returns:
        Hex digest of hashed password
    """
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify password against hash
    
    Args:
        password: Plain text password to verify
        password_hash: Stored password hash
        
    Returns:
        True if password matches
    """
    return hash_password(password) == password_hash


def generate_credentials(name: str) -> Tuple[str, str, str]:
    """
    Generate complete credentials set
    
    Args:
        name: User's name
        
    Returns:
        Tuple of (username, password, password_hash)
    """
    username = generate_username(name)
    password = generate_strong_password()
    password_hash = hash_password(password)
    
    logger.info(f"Generated credentials for: {name} -> {username}")
    
    return username, password, password_hash


class CredentialStorage:
    """Secure local storage for credentials using encrypted activation storage"""

    def __init__(self):
        self.use_keyring = False  # Deprecated, kept for compatibility logging
    
    def store_credentials(self, username: str, password: str) -> bool:
        """
        Store credentials securely
        
        Args:
            username: Username
            password: Password (will be hashed before storage)
            
        Returns:
            True if successful
        """
        try:
            logger.info(f"[STORE] Storing credentials for username: '{username}'")
            logger.info("[STORE] Keyring disabled - using encrypted activation storage only")
            self._store_fallback(username, password)
            logger.info(f"[STORE] Credentials stored securely for: {username}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to store credentials: {e}")
            return False
    
    def get_credentials(self, username: str) -> Optional[str]:
        """
        Retrieve stored password for username
        
        Args:
            username: Username
            
        Returns:
            Password or None if not found
        """
        try:
            return self._get_fallback(username)
        except Exception as e:
            logger.error(f"Failed to retrieve credentials: {e}")
            return None
    
    def verify_credentials(self, username: str, password: str) -> bool:
        """
        Verify username and password
        
        Args:
            username: Username
            password: Password to verify
            
        Returns:
            True if credentials are correct
        """
        logger.info(f"[VERIFY] Verifying credentials for username: '{username}'")
        logger.info("[VERIFY] Keyring disabled - using encrypted storage")
        
        stored_password = self.get_credentials(username)
        if stored_password is None:
            logger.warning(f"[VERIFY] No stored password found for username: '{username}'")
            return False
        
        logger.info(f"[VERIFY] Stored password found")
        logger.info(f"[VERIFY] Stored password length: {len(stored_password)}")
        
        logger.info("[VERIFY] Comparing password hashes")
        entered_hash = hash_password(password)
        logger.info(f"[VERIFY] Entered password hash: {entered_hash[:32]}...")
        logger.info(f"[VERIFY] Stored password hash: {stored_password[:32]}...")
        result = stored_password == entered_hash
        logger.info(f"[VERIFY] Hash comparison result: {result}")
        return result
    
    def delete_credentials(self, username: str) -> bool:
        """
        Delete stored credentials
        
        Args:
            username: Username
            
        Returns:
            True if successful
        """
        try:
            self._delete_fallback(username)
            
            logger.info(f"Credentials deleted for: {username}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete credentials: {e}")
            return False
    
    def get_stored_username(self) -> Optional[str]:
        """
        Get the stored username (if any)
        
        Returns:
            Username or None
        """
        try:
            # Try to read from activation data
            from .storage import ActivationStorage
            storage = ActivationStorage()
            data = storage.load_activation_data()
            
            if data and 'username' in data:
                return data['username']
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get stored username: {e}")
            return None
    
    # Fallback methods for when keyring is not available
    def _store_fallback(self, username: str, password: str):
        """Store credentials in encrypted activation storage"""
        from .storage import ActivationStorage
        storage = ActivationStorage()
        data = storage.load_activation_data() or {}
        data['stored_username'] = username
        data['stored_password'] = hash_password(password)
        storage.save_activation_data(data)
    
    def _get_fallback(self, username: str) -> Optional[str]:
        """Get credentials from encrypted activation storage"""
        from .storage import ActivationStorage
        storage = ActivationStorage()
        data = storage.load_activation_data()
        
        if data and data.get('stored_username') == username:
            # Return the password (stored as hash in fallback mode)
            return data.get('stored_password')
        
        return None
    
    def _delete_fallback(self, username: str):
        """Delete credentials from encrypted activation storage"""
        from .storage import ActivationStorage
        storage = ActivationStorage()
        data = storage.load_activation_data()
        
        if data:
            data.pop('stored_username', None)
            data.pop('stored_password', None)
            storage.save_activation_data(data)


if __name__ == "__main__":
    import sys
    import os
    
    # Fix Windows console encoding
    if sys.platform == "win32":
        os.system('chcp 65001 > nul')
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    
    # Test credential generation
    print("Testing Credential Generation...")
    print()
    
    # Test username generation
    print("1. Username Generation:")
    names = ["John Doe", "Jane Smith", "Bob Johnson Jr.", "Alice-Marie O'Connor"]
    for name in names:
        username = generate_username(name)
        print(f"   {name:30} -> {username}")
    print()
    
    # Test password generation
    print("2. Password Generation:")
    for i in range(3):
        password = generate_strong_password()
        print(f"   Password {i+1}: {password}")
    print()
    
    # Test complete credentials
    print("3. Complete Credentials:")
    username, password, password_hash = generate_credentials("Test User")
    print(f"   Username: {username}")
    print(f"   Password: {password}")
    print(f"   Hash: {password_hash[:32]}...")
    print()
    
    # Test password verification
    print("4. Password Verification:")
    print(f"   Correct password: {verify_password(password, password_hash)}")
    print(f"   Wrong password: {verify_password('wrongpassword', password_hash)}")
    print()
    
    # Test credential storage
    print("5. Credential Storage:")
    storage = CredentialStorage()
    print(f"   Keyring available: {storage.use_keyring}")
    
    if storage.store_credentials(username, password):
        print(f"   [OK] Stored credentials")
        
        retrieved = storage.get_credentials(username)
        if retrieved:
            print(f"   [OK] Retrieved credentials")
            print(f"   Verification: {storage.verify_credentials(username, password)}")
        
        storage.delete_credentials(username)
        print(f"   [OK] Deleted credentials")
    
    print()
    print("[OK] Test complete!")

