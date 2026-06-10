"""RSA key management for RS256 JWT signing and JWKS publication.

Security model:
- The **private** key never leaves this service and is never committed to
  source. It is either loaded from a configured PEM file, generated and
  persisted to that path, or (dev only) generated ephemerally in memory.
- The **public** key is published at the JWKS endpoint so the Client app can
  verify token signatures locally without ever contacting this service per
  request.

Each key has a stable `kid` (RFC 7638 JWK thumbprint). The token header carries
the `kid` so verifiers can select the right key and so key rotation works: a new
key produces a new `kid`, and stale verifier caches simply miss and refetch.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _b64url_uint(value: int) -> str:
    """Encode an unsigned integer as base64url (no padding), per JWK spec."""
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


@dataclass(frozen=True)
class KeyPair:
    private_pem: bytes
    public_pem: bytes
    kid: str
    _public_numbers: rsa.RSAPublicNumbers

    def public_jwk(self) -> dict[str, str]:
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": self.kid,
            "n": _b64url_uint(self._public_numbers.n),
            "e": _b64url_uint(self._public_numbers.e),
        }

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        return {"keys": [self.public_jwk()]}


def _thumbprint(public_numbers: rsa.RSAPublicNumbers) -> str:
    """RFC 7638 JWK thumbprint — a stable identifier derived from the key."""
    canonical = json.dumps(
        {
            "e": _b64url_uint(public_numbers.e),
            "kty": "RSA",
            "n": _b64url_uint(public_numbers.n),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    digest = hashlib.sha256(canonical).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _load_or_generate_private_key() -> rsa.RSAPrivateKey:
    settings = get_settings()
    path = settings.jwt_private_key_path

    if path:
        key_file = Path(path)
        if key_file.exists():
            logger.info("loading RSA private key", extra={"path": path})
            return serialization.load_pem_private_key(key_file.read_bytes(), password=None)

        logger.info("generating and persisting RSA private key", extra={"path": path})
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        # Restrict permissions where the OS supports it.
        try:
            key_file.chmod(0o600)
        except OSError:  # e.g. Windows — best effort
            pass
        return key

    logger.warning(
        "JWT_PRIVATE_KEY_PATH not set — generating an EPHEMERAL in-memory RSA key. "
        "Tokens will not survive a restart. Set JWT_PRIVATE_KEY_PATH in production."
    )
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@lru_cache
def get_key_pair() -> KeyPair:
    """Return the process-wide signing key pair (loaded/generated once)."""
    private_key = _load_or_generate_private_key()
    public_key = private_key.public_key()
    public_numbers = public_key.public_numbers()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return KeyPair(
        private_pem=private_pem,
        public_pem=public_pem,
        kid=_thumbprint(public_numbers),
        _public_numbers=public_numbers,
    )
