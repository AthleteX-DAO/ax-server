from web3 import Web3
from app.config import get_settings
from app.chain.contracts import get_contract

settings = get_settings()
w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
spot = get_contract(w3, settings.addresses.spot_market_proxy, "spot_market_proxy")
print(f"Connected to SpotMarketProxy: {spot.address}")

for i in range(1, 5):
    try:
        name = spot.functions.name(i).call()
        print(f"Market {i}: {name}")
    except Exception as e:
        print(f"Market {i}: Not found")
