"""
Admin Authentication Manager
Handles password encryption, storage, and verification for admin panel access
"""

import os
import base64
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet


class AdminAuthManager:
    """Manages admin password authentication with encryption"""
    
    def __init__(self):
        # Use centralized path helper for consistent path resolution
        from .path_helper import get_app_root
        app_root = get_app_root()
        
        # Use secure_config directory for password storage
        self.secure_dir = app_root / "secure_config"
        self.password_file = self.secure_dir / "admin_password.enc"
        
        # Ensure secure directory exists
        self.secure_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_encryption_key(self) -> bytes:
        """
        Generate encryption key from machine-specific data.
        This ties the password file to this installation.
        """
        # Salt is provided at build time (never stored in the repository)
        from pages.licensing.build_secrets import get_secret
        key = hashlib.sha256(get_secret("KRIDWINN_ADMIN_SALT")).digest()
        return base64.urlsafe_b64encode(key)
    
    def is_password_set(self) -> bool:
        """Check if admin password has been set"""
        return self.password_file.exists() and self.password_file.stat().st_size > 0
    
    def set_password(self, password: str) -> bool:
        """
        Set/update admin password with encryption
        
        Args:
            password: Plain text password (8-10 characters)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate password length
            if not (8 <= len(password) <= 10):
                return False
            
            # Encrypt password
            f = Fernet(self._get_encryption_key())
            encrypted = f.encrypt(password.encode('utf-8'))
            
            # Write to file
            with open(self.password_file, 'wb') as file:
                file.write(encrypted)
            
            return True
            
        except Exception as e:
            print(f"Error setting password: {e}")
            return False
    
    def verify_password(self, password: str) -> bool:
        """
        Verify password against stored encrypted password
        
        Args:
            password: Plain text password to verify
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            if not self.is_password_set():
                return False
            
            # Read encrypted password
            with open(self.password_file, 'rb') as file:
                encrypted = file.read()
            
            # Decrypt and compare
            f = Fernet(self._get_encryption_key())
            stored_password = f.decrypt(encrypted).decode('utf-8')
            
            return password == stored_password
            
        except Exception as e:
            print(f"Error verifying password: {e}")
            return False
    
    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Change admin password
        
        Args:
            old_password: Current password for verification
            new_password: New password to set (8-10 characters)
            
        Returns:
            True if successful, False otherwise
        """
        # Verify old password first
        if not self.verify_password(old_password):
            return False
        
        # Set new password
        return self.set_password(new_password)
    
    def reset_password(self) -> bool:
        """
        Reset password (delete password file)
        WARNING: This should only be used for recovery
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.password_file.exists():
                self.password_file.unlink()
            return True
        except Exception as e:
            print(f"Error resetting password: {e}")
            return False
