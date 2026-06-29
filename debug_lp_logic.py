import sys, json
sys.path.append("/app")

import logging
logging.basicConfig(level=logging.DEBUG)

from app.api.v1.predict import get_chain_provider_optional, _get_markets
from pathlib import Path
from app.chain.contracts import get_contract

provider = get_chain_provider_optional()
markets = _get_markets()
m = next(m for m in markets if m.id == 25)

registry_path = Path("/app/data/markets_registry.json")
registry = json.loads(registry_path.read_text())

updates = {}
for rm in registry.get("markets", []):
    if rm.get("market_address", "").lower() == m.market_address.lower() and rm.get("yes_pair_address") and rm.get("no_pair_address"):
        w3 = provider.w3 if provider else None
        print("W3 IS:", w3)
        if w3:
            yes_pair = get_contract(w3, rm["yes_pair_address"], "uniswap_v2_pair")
            yes_reserves = yes_pair.functions.getReserves().call()
            yes_token0 = yes_pair.functions.token0().call()
            print("YES RESERVES:", yes_reserves, "TOKEN0:", yes_token0)

            if yes_token0.lower() == rm["yes_token"].lower():
                yes_token_reserve, yes_usd_reserve = yes_reserves[0], yes_reserves[1]
            else:
                yes_usd_reserve, yes_token_reserve = yes_reserves[0], yes_reserves[1]

            if yes_token_reserve > 0:
                yes_price = round(yes_usd_reserve / yes_token_reserve, 4)
                updates["yes_price"] = min(yes_price, 1.0)
                updates["no_price"] = round(1 - updates["yes_price"], 4)
                print("UPDATES AFTER YES:", updates)
        
            # no pair
            try:
                no_pair = get_contract(w3, rm["no_pair_address"], "uniswap_v2_pair")
                no_reserves = no_pair.functions.getReserves().call()
                no_token0 = no_pair.functions.token0().call()
                print("NO RESERVES:", no_reserves, "TOKEN0:", no_token0)

                if no_token0.lower() == rm["no_token"].lower():
                    no_token_reserve, no_usd_reserve = no_reserves[0], no_reserves[1]
                else:
                    no_usd_reserve, no_token_reserve = no_reserves[0], no_reserves[1]

                if no_token_reserve > 0:
                    no_price = round(no_usd_reserve / no_token_reserve, 4)
                    updates["no_price"] = min(no_price, 1.0)
                    if "yes_price" in updates:
                        total = updates["yes_price"] + updates["no_price"]
                        if total > 0:
                            updates["yes_price"] = round(updates["yes_price"] / total, 4)
                            updates["no_price"] = round(updates["no_price"] / total, 4)
                    print("UPDATES AFTER NO:", updates)
            except Exception as e:
                print("NO PAIR ERROR:", e)
        break

print("FINAL UPDATES:", updates)
