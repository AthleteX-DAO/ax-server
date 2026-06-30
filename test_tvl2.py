import asyncio
from app.config import get_settings
from web3 import Web3
import json

async def main():
    settings = get_settings()
    w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
    
    # Load ERC20 ABI
    with open('/home/boltik/code/ax-server/abis/erc20.json') as f:
        erc20_abi = json.load(f)
        
    ax_token_addr = w3.to_checksum_address(settings.addresses.ax_token)
    core_proxy_addr = w3.to_checksum_address(settings.addresses.core_proxy)
    
    ax_token = w3.eth.contract(address=ax_token_addr, abi=erc20_abi)
    balance = ax_token.functions.balanceOf(core_proxy_addr).call()
    
    print(f"Total AX in Core Proxy: {balance} ({balance/1e18} AX)")
        
if __name__ == "__main__":
    asyncio.run(main())
