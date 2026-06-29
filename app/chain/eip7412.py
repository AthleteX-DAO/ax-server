import logging
import re
import httpx
import eth_abi
from web3 import Web3
from typing import Any

logger = logging.getLogger("ax-server.chain.eip7412")

MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
MULTICALL3_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bool", "name": "requireSuccess", "type": "bool"},
                    {"internalType": "uint256", "name": "value", "type": "uint256"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"}
                ],
                "internalType": "struct Multicall3.Call3Value[]",
                "name": "calls",
                "type": "tuple[]"
            }
        ],
        "name": "aggregate3Value",
        "outputs": [{"internalType": "tuple[]", "name": "returnCode", "type": "tuple[]"}],
        "stateMutability": "payable",
        "type": "function"
    }
]

PYTH_WRAPPER_ABI = [
    {
        "inputs": [{"name": "updateData", "type": "bytes"}],
        "name": "fulfillOracleQuery",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    }
]

def extract_revert_data(e: Exception) -> str | None:
    if hasattr(e, "data") and e.data:
        if isinstance(e.data, str): return e.data
        if isinstance(e.data, dict) and "data" in e.data: return e.data["data"]
    if hasattr(e, "args") and len(e.args) > 0:
        arg = e.args[0]
        if isinstance(arg, dict) and "data" in arg:
            return arg["data"]
        elif isinstance(arg, str):
            m = re.search(r"0x[0-9a-fA-F]+", arg)
            if m: return m.group(0)
    
    # Try string representation as last resort
    err_str = str(e)
    m = re.search(r"0x[0-9a-fA-F]{64,}", err_str)
    if m:
        return m.group(0)
        
    return None

def try_resolve_eip7412(w3: Web3, e: Exception, original_tx: dict[str, Any]) -> dict[str, Any] | None:
    """Try to intercept an EIP-7412 OracleDataRequired revert and build a Multicall3 payload."""
    revert_hex = extract_revert_data(e)
    if not revert_hex or not revert_hex.startswith("0xc2a825f5"):
        return None
        
    try:
        revert_bytes = bytes.fromhex(revert_hex[10:])
        oracle_contract, oracle_query = eth_abi.decode(["address", "bytes"], revert_bytes)
        
        # Parse Synthetix Pyth oracle_query format
        tag, pyth_data = eth_abi.decode(["uint8", "bytes"], oracle_query)
        if tag != 1:
            logger.warning(f"Unknown oracleQuery tag {tag}")
            return None
            
        feed_id, _ = eth_abi.decode(["bytes32", "uint256"], pyth_data)
        feed_id_hex = feed_id.hex()
        
        # Fetch VAA from Hermes
        url = f"https://hermes.pyth.network/v2/updates/price/latest?ids[]={feed_id_hex}"
        logger.info(f"Fetching Pyth data for feed {feed_id_hex}")
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        update_data = bytes.fromhex(resp.json()["binary"]["data"][0])
        
        # Encode fulfillOracleQuery
        wrapper_contract = w3.eth.contract(address=oracle_contract, abi=PYTH_WRAPPER_ABI)
        fulfill_calldata = wrapper_contract.encodeABI(fn_name="fulfillOracleQuery", args=[update_data])
        
        # Build Multicall3 payload
        pyth_fee = 1  # 1 wei on Polygon
        calls = [
            {
                "target": oracle_contract,
                "requireSuccess": True,
                "value": pyth_fee,
                "callData": bytes.fromhex(fulfill_calldata[2:])
            },
            {
                "target": original_tx["to"],
                "requireSuccess": True,
                "value": int(original_tx.get("value", 0)),
                "callData": bytes.fromhex(original_tx["data"][2:] if original_tx["data"].startswith("0x") else original_tx["data"])
            }
        ]
        
        multicall = w3.eth.contract(address=MULTICALL3_ADDRESS, abi=MULTICALL3_ABI)
        multicall_data = multicall.encodeABI(fn_name="aggregate3Value", args=[calls])
        
        total_value = pyth_fee + int(original_tx.get("value", 0))
        
        return {
            "to": MULTICALL3_ADDRESS,
            "data": multicall_data,
            "value": str(total_value),
            "chain_id": original_tx["chain_id"]
        }
        
    except Exception as parse_err:
        logger.warning(f"Failed to resolve EIP-7412 revert: {parse_err}")
        return None
