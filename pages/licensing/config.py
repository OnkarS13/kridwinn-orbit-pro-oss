"""
Licensing Configuration Module
Simplified for offline RSA-signed license system.
"""


class LicensingConfig:
    """Configuration for the offline licensing system"""

    def __init__(self):
        self.config = {
            "licensing": {
                "trial_default_days": 7,
                "require_activation": True,
            },
            "app": {
                "name": "Kridwinn Orbit Pro",
                "version": "1.0.0",
                "require_license": True,
            },
        }

    def get(self, key_path: str, default=None):
        """Get configuration value by dot-notation path"""
        keys = key_path.split(".")
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    @property
    def licensing_enabled(self) -> bool:
        return self.get("app.require_license", False)


_global_config = None


def get_config() -> LicensingConfig:
    """Get global configuration instance"""
    global _global_config
    if _global_config is None:
        _global_config = LicensingConfig()
    return _global_config
