import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent))

import traceback
from web3 import Web3
from app.config import get_settings

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

def main():
    settings = get_settings()
    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
    addr = w3.to_checksum_address("0xacD7B3D9c10e47eed0e449F3ff23715bE0f12B5f")
    contract = w3.eth.contract(address=addr, abi=ERC20_ABI)
    
    print("Querying name...")
    try:
        name = contract.functions.name().call()
        print("Name:", name)
    except Exception as e:
        print("Failed to query name:")
        traceback.print_exc()
        
    print("\nQuerying symbol...")
    try:
        symbol = contract.functions.symbol().call()
        print("Symbol:", symbol)
    except Exception as e:
        print("Failed to query symbol:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
