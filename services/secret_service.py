# ForgePrompt — SecretService
# Provides symmetric encryption for organization secrets stored at rest.
#
# Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package —
# a well-audited, OWASP-approved approach for secrets at rest.
#
# Setup:
#   1. Generate a key once:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   2. Store the key in .env as  SECRET_ENCRYPTION_KEY=<value>
#   3. Never commit the key to source control.
#
# Backward compatibility:
#   If a stored value cannot be decrypted with Fernet (e.g. it was stored
#   before this migration as plain base64), decrypt_secret() falls back to
#   base64-decoding so that old secrets are still readable until they are
#   re-saved through the new encrypt path.

from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key bootstrap
# ---------------------------------------------------------------------------

def _load_fernet():
    """
    Lazily load the Fernet cipher.  Returns None if the cryptography package
    is not installed, so the service degrades gracefully (with a warning)
    rather than crashing at import time.
    """
    try:
        from cryptography.fernet import Fernet, InvalidToken  # noqa: F401
        raw_key = os.environ.get("SECRET_ENCRYPTION_KEY", "").strip()
        if not raw_key:
            logger.warning(
                "[SecretService] SECRET_ENCRYPTION_KEY is not set. "
                "Secrets will be stored as base64 (not encrypted). "
                "Generate a key with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
            return None
        return Fernet(raw_key.encode())
    except ImportError:
        logger.warning(
            "[SecretService] 'cryptography' package not installed. "
            "Run: pip install cryptography==42.0.8"
        )
        return None
    except Exception as exc:
        logger.error("[SecretService] Failed to initialise Fernet: %s", exc)
        return None


# Module-level cipher instance (initialised once on first use).
_fernet = None
_fernet_initialised = False


def _get_fernet():
    global _fernet, _fernet_initialised
    if not _fernet_initialised:
        _fernet = _load_fernet()
        _fernet_initialised = True
    return _fernet


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encrypt_secret(plaintext: str) -> str:
    """
    Encrypt *plaintext* and return a string safe to store in the database.

    If Fernet is available the returned string is a Fernet token (URL-safe
    base64).  If Fernet is unavailable (missing key / missing package) it
    falls back to plain base64 so the application still works — just without
    encryption-at-rest.

    Args:
        plaintext: The raw secret value.

    Returns:
        Encrypted (or base64-encoded) string.
    """
    fernet = _get_fernet()
    if fernet is not None:
        try:
            return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            logger.error("[SecretService] Encryption failed, falling back to base64: %s", exc)
    # Fallback — at least mask the value in the DB.
    return base64.b64encode(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(stored_value: str) -> Optional[str]:
    """
    Decrypt a value previously produced by :func:`encrypt_secret`.

    Handles two cases transparently:
      * Fernet token  → decrypted with Fernet.
      * Legacy base64 → decoded with base64 (backward compat for values
        stored before this module was introduced).

    Args:
        stored_value: The encrypted/encoded string from the database.

    Returns:
        The plaintext secret, or the original ``stored_value`` if all
        decryption attempts fail (so existing workflows are not broken).
    """
    if not stored_value:
        return stored_value

    fernet = _get_fernet()
    if fernet is not None:
        try:
            from cryptography.fernet import InvalidToken
            return fernet.decrypt(stored_value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Not a Fernet token — probably a legacy base64 value.
            pass
        except Exception as exc:
            logger.warning("[SecretService] Fernet decryption failed: %s", exc)

    # Fallback: try plain base64.
    try:
        return base64.b64decode(stored_value.encode("utf-8")).decode("utf-8")
    except Exception:
        # Return as-is if nothing works.
        logger.warning("[SecretService] Could not decode stored secret value; returning raw.")
        return stored_value
