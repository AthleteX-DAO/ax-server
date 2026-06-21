"""SIWE (Sign-In with Ethereum) — EIP-4361 message generation and verification.

Implements the server-side of the SIWE flow:
1. Generate a nonce for the client
2. Build a standards-compliant EIP-4361 message
3. Verify the signed message and recover the signer address

References
----------
- https://eips.ethereum.org/EIPS/eip-4361
- https://login.xyz
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from eth_account import Account
from eth_account.messages import encode_defunct

logger = logging.getLogger("ax-server.auth.siwe")

# ── Nonce store (in-memory, production should use Redis) ────────────────

_NONCE_TTL = 300  # 5 minutes


@dataclass
class _NonceEntry:
    nonce: str
    created_at: float
    used: bool = False


class NonceStore:
    """In-memory nonce store with TTL expiration.

    Production deployments should swap this for Redis or similar.
    """

    def __init__(self, ttl: int = _NONCE_TTL) -> None:
        self._store: dict[str, _NonceEntry] = {}
        self._ttl = ttl

    def generate(self) -> str:
        """Generate a cryptographically random nonce."""
        nonce = secrets.token_hex(16)
        self._store[nonce] = _NonceEntry(nonce=nonce, created_at=time.time())
        self._cleanup()
        return nonce

    def validate(self, nonce: str) -> bool:
        """Validate and consume a nonce (single-use).

        Returns ``True`` if the nonce is valid and unused.
        """
        entry = self._store.get(nonce)
        if not entry:
            return False
        if entry.used:
            return False
        if time.time() - entry.created_at > self._ttl:
            del self._store[nonce]
            return False
        entry.used = True
        return True

    def _cleanup(self) -> None:
        """Remove expired nonces."""
        now = time.time()
        expired = [k for k, v in self._store.items() if now - v.created_at > self._ttl]
        for k in expired:
            del self._store[k]


# Singleton
nonce_store = NonceStore()


# ── EIP-4361 Message ────────────────────────────────────────────────────

_EIP4361_TEMPLATE = """{domain} wants you to sign in with your Ethereum account:
{address}

{statement}

URI: {uri}
Version: {version}
Chain ID: {chain_id}
Nonce: {nonce}
Issued At: {issued_at}"""

_EIP4361_WITH_EXPIRY = _EIP4361_TEMPLATE + "\nExpiration Time: {expiration_time}"


@dataclass
class SIWEMessage:
    """Parsed EIP-4361 message."""

    domain: str
    address: str
    statement: str
    uri: str
    version: str
    chain_id: int
    nonce: str
    issued_at: str
    expiration_time: str | None = None


def build_siwe_message(
    address: str,
    nonce: str,
    *,
    domain: str = "athletex.io",
    chain_id: int = 137,
    statement: str = "Sign in to AthleteX to access your portfolio and place orders.",
    uri: str = "https://athletex.io",
    expiry_minutes: int = 10,
) -> str:
    """Build a standards-compliant EIP-4361 SIWE message.

    Parameters
    ----------
    address:
        Ethereum address (checksummed).
    nonce:
        Server-generated nonce from ``NonceStore.generate()``.
    domain:
        The requesting domain (e.g. athletex.io).
    chain_id:
        EIP-155 chain ID (137 for Polygon).
    statement:
        Human-readable statement shown to the user.
    expiry_minutes:
        Message expiry in minutes.

    Returns
    -------
    str
        The EIP-4361 formatted message for the user to sign.
    """
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(minutes=expiry_minutes)

    return _EIP4361_WITH_EXPIRY.format(
        domain=domain,
        address=address,
        statement=statement,
        uri=uri,
        version="1",
        chain_id=chain_id,
        nonce=nonce,
        issued_at=now.isoformat(timespec="seconds"),
        expiration_time=expiry.isoformat(timespec="seconds"),
    )


# ── Verification ────────────────────────────────────────────────────────

_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")
_NONCE_RE = re.compile(r"Nonce: ([a-f0-9]+)")
_CHAIN_RE = re.compile(r"Chain ID: (\d+)")
_EXPIRY_RE = re.compile(r"Expiration Time: (.+)")


def parse_siwe_message(message: str) -> SIWEMessage:
    """Parse key fields from an EIP-4361 message string.

    Raises ``ValueError`` on malformed messages.
    """
    lines = message.strip().split("\n")

    if len(lines) < 8:
        raise ValueError("Message too short to be valid EIP-4361")

    # Line 0: "{domain} wants you to sign in with your Ethereum account:"
    domain_match = lines[0].split(" wants you to sign in")[0]

    # Line 1: address
    addr_match = _ADDRESS_RE.search(lines[1])
    if not addr_match:
        raise ValueError("No valid Ethereum address found")
    address = addr_match.group()

    # Nonce
    nonce_match = _NONCE_RE.search(message)
    if not nonce_match:
        raise ValueError("No nonce found")
    nonce = nonce_match.group(1)

    # Chain ID
    chain_match = _CHAIN_RE.search(message)
    chain_id = int(chain_match.group(1)) if chain_match else 137

    # Expiration
    expiry_match = _EXPIRY_RE.search(message)
    expiration_time = expiry_match.group(1) if expiry_match else None

    return SIWEMessage(
        domain=domain_match,
        address=address,
        statement="",  # extracted but not critical for verification
        uri="",
        version="1",
        chain_id=chain_id,
        nonce=nonce,
        issued_at="",
        expiration_time=expiration_time,
    )


def verify_siwe(
    message: str,
    signature: str,
    *,
    expected_domain: str | None = None,
    expected_chain_id: int | None = None,
) -> str:
    """Verify a signed EIP-4361 message and return the signer address.

    Parameters
    ----------
    message:
        The full EIP-4361 message string that was signed.
    signature:
        The hex-encoded signature (with or without 0x prefix).

    Returns
    -------
    str
        Checksummed Ethereum address of the signer.

    Raises
    ------
    ValueError
        If signature is invalid, nonce is consumed, or message is expired.
    """
    # Parse the message
    parsed = parse_siwe_message(message)

    # Verify nonce (single-use)
    if not nonce_store.validate(parsed.nonce):
        raise ValueError(f"Invalid or expired nonce: {parsed.nonce}")

    # Check expiration
    if parsed.expiration_time:
        try:
            expiry = datetime.fromisoformat(parsed.expiration_time)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > expiry:
                raise ValueError("SIWE message has expired")
        except (ValueError, TypeError) as e:
            if "expired" in str(e):
                raise
            logger.warning("Could not parse expiration time: %s", e)

    # Check domain
    if expected_domain and parsed.domain != expected_domain:
        raise ValueError(f"Domain mismatch: expected {expected_domain}, got {parsed.domain}")

    # Check chain ID
    if expected_chain_id and parsed.chain_id != expected_chain_id:
        raise ValueError(
            f"Chain ID mismatch: expected {expected_chain_id}, got {parsed.chain_id}"
        )

    # Recover signer from signature
    try:
        signable = encode_defunct(text=message)
        recovered = Account.recover_message(signable, signature=signature)
    except Exception as e:
        raise ValueError(f"Invalid signature: {e}") from e

    # Verify recovered address matches the one in the message
    if recovered.lower() != parsed.address.lower():
        raise ValueError(
            f"Signer mismatch: message claims {parsed.address}, "
            f"but signature recovers {recovered}"
        )

    logger.info("SIWE verified for %s on chain %d", recovered, parsed.chain_id)
    return recovered
