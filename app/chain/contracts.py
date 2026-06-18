"""Contract loader — reads ABIs and creates web3 contract instances.

All ABI files live in the /abis directory as JSON arrays.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from web3 import Web3
from web3.contract import Contract

logger = logging.getLogger("ax-server.chain.contracts")

ABI_DIR = Path(__file__).resolve().parent.parent.parent / "abis"


def load_abi(name: str) -> list[dict[str, Any]]:
    """Load an ABI JSON file from the abis/ directory.

    Args:
        name: Filename without extension (e.g. 'core_proxy').

    Returns:
        Parsed ABI as a list of dicts.
    """
    path = ABI_DIR / f"{name}.json"
    if not path.exists():
        logger.warning("ABI file not found: %s", path)
        return []
    with open(path) as f:
        return json.load(f)


def get_contract(w3: Web3, address: str, abi_name: str) -> Contract:
    """Create a web3 Contract instance.

    Args:
        w3: Web3 instance.
        address: Checksummed contract address.
        abi_name: Name of the ABI file (without .json).

    Returns:
        Web3 Contract object.
    """
    abi = load_abi(abi_name)
    return w3.eth.contract(
        address=Web3.to_checksum_address(address),
        abi=abi,
    )
