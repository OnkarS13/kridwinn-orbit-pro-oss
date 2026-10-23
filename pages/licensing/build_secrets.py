"""
Build-time secret resolution.

Secret values are never stored in the repository. They are resolved, in order, from:
  1. ``pages/licensing/_build_secrets.py`` - generated at build time by
     ``tools/write_build_secrets.py`` (git-ignored, compiled into the binary).
  2. Environment variables with the same names (useful for local development).

Required names:
  KRIDWINN_CONFIG_KEY       Fernet key that decrypts secure_config/*.enc
  KRIDWINN_ACTIVATION_SALT  Salt used to derive the activation_data.enc key
  KRIDWINN_ADMIN_SALT       Salt used to derive the admin password store key
"""

from __future__ import annotations

import os

try:  # Generated at build time; absent in a fresh checkout.
    from . import _build_secrets as _generated  # type: ignore
except ImportError:  # pragma: no cover - depends on build environment
    _generated = None

SECRET_NAMES = ("KRIDWINN_CONFIG_KEY", "KRIDWINN_ACTIVATION_SALT", "KRIDWINN_ADMIN_SALT")


def get_secret(name: str) -> bytes:
    """Return the secret ``name`` as bytes, or raise RuntimeError if it is not configured."""
    if name not in SECRET_NAMES:
        raise KeyError(f"Unknown build secret: {name}")

    value = getattr(_generated, name, None) if _generated is not None else None
    if not value:
        value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Build secret '{name}' is not configured. Run tools/write_build_secrets.py "
            f"with the {name} environment variable set, or export it before starting the app."
        )
    return value.encode("utf-8") if isinstance(value, str) else value
