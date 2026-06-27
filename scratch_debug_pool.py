import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

from web3 import Web3
from app.config import get_settings
from app.chain.contracts import get_contract

ADDITIONAL_ABI = [
    {
        "type": "function",
        "name": "getPoolConfiguration",
        "inputs": [{"name": "poolId", "type": "uint128"}],
        "outputs": [
            {
                "name": "markets",
                "type": "tuple[]",
                "components": [
                    {"name": "marketId", "type": "uint128"},
                    {"name": "weightD18", "type": "uint256"},
                    {"name": "maxDebtShareValueD18", "type": "int256"}
                ]
            }
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "getPoolName",
        "inputs": [{"name": "poolId", "type": "uint128"}],
        "outputs": [{"name": "name", "type": "string"}],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "getPoolOwner",
        "inputs": [{"name": "poolId", "type": "uint128"}],
        "outputs": [{"name": "owner", "type": "address"}],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "getVaultCollateral",
        "inputs": [
            {"name": "poolId", "type": "uint128"},
            {"name": "collateralType", "type": "address"}
        ],
        "outputs": [
            {"name": "amount", "type": "uint256"},
            {"name": "value", "type": "uint256"}
        ],
        "stateMutability": "view"
    },
    {
        "type": "function",
        "name": "getVaultDebt",
        "inputs": [
            {"name": "poolId", "type": "uint128"},
            {"name": "collateralType", "type": "address"}
        ],
        "outputs": [
            {"name": "debt", "type": "int256"}
        ],
        "stateMutability": "view"
    }
]

def main():
    settings = get_settings()
    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
    
    # Load CoreProxy and extend ABI
    core = get_contract(w3, settings.addresses.core_proxy, "core_proxy")
    extended_abi = list(core.abi) + ADDITIONAL_ABI
    core = w3.eth.contract(address=core.address, abi=extended_abi)
    
    pool_id = 1
    print(f"Querying Pool {pool_id} status...")
    
    try:
        try:
            name = core.functions.getPoolName(pool_id).call()
            print("Pool Name:", name)
        except Exception:
            print("Failed to get pool name")
            
        try:
            owner = core.functions.getPoolOwner(pool_id).call()
            print("Pool Owner:", owner)
        except Exception:
            print("Failed to get pool owner")
            
        try:
            config = core.functions.getPoolConfiguration(pool_id).call()
            print("\nPool Configuration (Markets):")
            for m in config:
                print(f"- Market ID: {m[0]}")
                print(f"  Weight: {m[1]/1e18:.2f}")
                print(f"  Max Debt Share Value: {m[2]/1e18:.2f}")
        except Exception as e:
            print("Failed to get pool configuration:", e)
            
        # Check AX token vault state
        ax_token = w3.to_checksum_address(settings.addresses.ax_token)
        try:
            vault_collateral = core.functions.getVaultCollateral(pool_id, ax_token).call()
            vault_debt = core.functions.getVaultDebt(pool_id, ax_token).call()
            print(f"\nAX Vault state (Pool {pool_id}):")
            print(f"- Total Collateral Deposited: {vault_collateral[0]/1e18:.2f} AX")
            print(f"- Total Collateral Value: ${vault_collateral[1]/1e18:.2f} USD")
            print(f"- Total Vault Debt: ${vault_debt/1e18:.2f} USD")
        except Exception as e:
            print("Failed to get AX Vault state:", e)
            
    except Exception as e:
        print("General error:", e)

if __name__ == "__main__":
    main()
