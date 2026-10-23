"""
License Key Generator
Generates and manages license keys
"""

import secrets
import string
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


def generate_license_key() -> str:
    """
    Generate a unique license key in format: LIC-XXXX-XXXX-XXXX-XXXX
    
    Returns:
        str: Generated license key
    """
    chars = string.ascii_uppercase + string.digits
    parts = ['LIC']
    
    for _ in range(4):
        part = ''.join(secrets.choice(chars) for _ in range(4))
        parts.append(part)
    
    return '-'.join(parts)


def create_license_data(
    user_name: str,
    user_email: str,
    trial_days: int = 7,
    phone: str = "",
    company: str = "",
    created_by: str = "system",
    created_by_role: str = "master"
) -> Dict[str, Any]:
    """
    Create complete license data structure
    
    Args:
        user_name: User's full name
        user_email: User's email
        trial_days: Trial period in days
        phone: User's phone (optional)
        company: User's company (optional)
        created_by: ID of creator (admin/assistant)
        created_by_role: Role of creator
        
    Returns:
        Dictionary with complete license data
    """
    license_key = generate_license_key()
    now = datetime.now()
    expires_at = now + timedelta(days=trial_days)
    
    return {
        'license_key': license_key,
        'machine_id': None,  # Will be set on activation
        'user_info': {
            'name': user_name,
            'email': user_email,
            'phone': phone,
            'company': company
        },
        'created_by': created_by,
        'created_by_role': created_by_role,
        'created_at': now.isoformat(),
        'expires_at': expires_at.isoformat(),
        'trial_days': trial_days,
        'status': 'pending',  # pending -> active (on first activation)
        'first_activation': None,
        'last_check_in': None,
        'total_launches': 0,
        'revoke_action': 'block',  # block | destroy | message
        'grace_period_days': 2,
        'is_blocked': False
    }


def validate_license_key_format(license_key: str) -> bool:
    """
    Validate license key format
    
    Args:
        license_key: License key to validate
        
    Returns:
        bool: True if valid format
    """
    parts = license_key.split('-')
    
    if len(parts) != 5:
        return False
    
    if parts[0] != 'LIC':
        return False
    
    for part in parts[1:]:
        if len(part) != 4:
            return False
        if not part.isalnum():
            return False
    
    return True


if __name__ == "__main__":
    # Test license generation
    print("=" * 60)
    print("License Key Generator Test")
    print("=" * 60)
    
    # Generate 5 sample keys
    print("\n1. Generating 5 sample license keys:")
    for i in range(5):
        key = generate_license_key()
        valid = validate_license_key_format(key)
        print(f"   {i+1}. {key} - {'✅ Valid' if valid else '❌ Invalid'}")
    
    # Create sample license data
    print("\n2. Creating sample license data:")
    license_data = create_license_data(
        user_name="John Doe",
        user_email="john@example.com",
        trial_days=7,
        phone="+1234567890",
        company="ABC Corp",
        created_by="master_001"
    )
    
    print(f"   License Key: {license_data['license_key']}")
    print(f"   User: {license_data['user_info']['name']}")
    print(f"   Email: {license_data['user_info']['email']}")
    print(f"   Trial Days: {license_data['trial_days']}")
    print(f"   Expires: {license_data['expires_at']}")
    print(f"   Status: {license_data['status']}")
    
    # Test validation
    print("\n3. Testing license key validation:")
    test_keys = [
        "LIC-AB12-CD34-EF56-GH78",  # Valid
        "LIC-1234-5678-ABCD-EFGH",  # Valid
        "LIC-ABC-DEF-GHI-JKL",      # Invalid (too short)
        "ABC-1234-5678-ABCD-EFGH",  # Invalid (wrong prefix)
        "LIC-1234-5678-ABCD",       # Invalid (missing part)
    ]
    
    for key in test_keys:
        valid = validate_license_key_format(key)
        print(f"   {key}: {'✅ Valid' if valid else '❌ Invalid'}")
    
    print("\n" + "=" * 60)
    print("✅ Test Complete!")
    print("=" * 60)

