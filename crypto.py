"""
Zentiqa — credential encryption.

Encrypts the MT5 investor password (read-only login) before it is
stored, and decrypts it only in memory, only when needed to call the
broker gateway. Never log or print a decrypted value.

The master key MUST come from the environment in production — never
hardcode it, never commit it. Generate one once with:

    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

...and set it as the ZENTIQA_MASTER_KEY environment variable wherever
the app runs (and nowhere else).
"""

import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.environ.get("ZENTIQA_MASTER_KEY")
    if not key:
        raise RuntimeError(
            "ZENTIQA_MASTER_KEY is not set. Generate one with "
            "Fernet.generate_key() and set it as an environment variable "
            "before running the app. Do not hardcode it."
        )
    return Fernet(key.encode())


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential (e.g. MT5 investor password) for storage."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a stored credential. Raises ValueError if the key is wrong
    or the data was tampered with/corrupted."""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Could not decrypt credential — wrong key or corrupted data.") from e
