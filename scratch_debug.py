import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

from web3 import Web3
from app.config import get_settings
from app.chain.contracts import get_contract

# Minimal ERC20 ABI to query name and symbol
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    }
]

ADDITIONAL_ABI = [
    {
        "type": "function",
        "name": "getCollateralConfigurations",
        "inputs": [
            {
                "name": "hideDisabled",
                "type": "bool"
            }
        ],
        "outputs": [
            {
                "name": "",
                "type": "tuple[]",
                "components": [
                    {"name": "depositingEnabled", "type": "bool"},
                    {"name": "issuanceRatioD18", "type": "uint256"},
                    {"name": "liquidationRatioD18", "type": "uint256"},
                    {"name": "liquidationRewardD18", "type": "uint256"},
                    {"name": "oracleNodeId", "type": "bytes32"},
                    {"name": "tokenAddress", "type": "address"},
                    {"name": "minDelegationD18", "type": "uint256"}
                ]
            }
        ],
        "stateMutability": "view"
    }
]

def main():
    settings = get_settings()
    rpc_url = settings.polygon_rpc_url
    print(f"Connecting to RPC: {rpc_url}")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("Failed to connect to RPC")
        return
    print(f"Connected. Block number: {w3.eth.block_number}")
    
    # Load CoreProxy and extend ABI
    core = get_contract(w3, settings.addresses.core_proxy, "core_proxy")
    extended_abi = list(core.abi) + ADDITIONAL_ABI
    core = w3.eth.contract(address=core.address, abi=extended_abi)
    
    try:
        # Get collateral configurations
        configs = core.functions.getCollateralConfigurations(False).call()
        print(f"\nCollateral Configurations (Total {len(configs)}):")
        for c in configs:
            addr = w3.to_checksum_address(c[5])
            erc20 = w3.eth.contract(address=addr, abi=ERC20_ABI)
            try:
                name = erc20.functions.name().call()
                symbol = erc20.functions.symbol().call()
                decimals = erc20.functions.decimals().call()
            except Exception:
                name, symbol, decimals = "Unknown", "Unknown", 18
                
            print(f"- Token Address: {addr} ({name} / {symbol})")
            print(f"  Depositing Enabled: {c[0]}")
            print(f"  Issuance Ratio: {c[1] / 10**decimals:.2f}")
            print(f"  Liquidation Ratio: {c[2] / 10**decimals:.2f}")
            print(f"  Min Delegation Raw: {c[6]}")
            print(f"  Min Delegation: {c[6] / 10**decimals:.2f}")
    except Exception as e:
        print(f"Error querying CoreProxy: {e}")

if __name__ == "__main__":
    main()
