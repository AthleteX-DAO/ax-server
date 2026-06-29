import sys, json
sys.path.append("/app")
try:
    from app.api.v1.predict import get_chain_provider_optional
    provider = get_chain_provider_optional()
    print("PROVIDER:", provider)
    
    from pathlib import Path
    registry_path = Path("/app/data/markets_registry.json")
    print("REGISTRY EXISTS:", registry_path.exists())
    if registry_path.exists():
        registry = json.loads(registry_path.read_text())
        print("JELLY ROLL IN REGISTRY:", any(rm.get("market_address", "").lower() == "0x164c1b6e1c9f3c088d3930ede9fca4ea8c11ad9f" for rm in registry.get("markets", [])))
        
        if provider:
            from app.chain.contracts import get_contract
            yes_pair = get_contract(provider.w3, "0xc33831197e77d956C83a0A00f8f9c6c52b761fD8", "uniswap_v2_pair")
            reserves = yes_pair.functions.getReserves().call()
            print("RESERVES:", reserves)
except Exception as e:
    import traceback
    traceback.print_exc()
