import asyncio
from app.chain.synthetix import SynthetixClient
from app.config import get_settings
from web3 import Web3
import traceback

async def main():
    try:
        settings = get_settings()
        w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
        client = SynthetixClient(w3, settings.addresses)
        
        pool_id = client.get_preferred_pool()
        print(f"Preferred pool: {pool_id}")
        
        colls = [client.addresses.ax_token]
        for c in colls:
            print(f"Checking collateral: {c}")
            amt, val = client.get_vault_collateral(pool_id, c)
            print(f"Amount: {amt} ({amt/1e18})")
            print(f"Value: {val} ({val/1e18})")
    except Exception as e:
        traceback.print_exc()
        
if __name__ == "__main__":
    asyncio.run(main())
