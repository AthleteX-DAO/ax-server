from web3 import Web3
from app.config import get_settings
from app.chain.contracts import get_contract

ADDITIONAL_ABI = [
    {
        "type": "function",
        "name": "getCollateralConfigurations",
        "inputs": [{"name": "hideDisabled", "type": "bool"}],
        "outputs": [
            {
                "name": "", "type": "tuple[]",
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

settings = get_settings()
w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
core = get_contract(w3, settings.addresses.core_proxy, "core_proxy")
core = w3.eth.contract(address=core.address, abi=list(core.abi) + ADDITIONAL_ABI)

configs = core.functions.getCollateralConfigurations(False).call()
for c in configs:
    addr = c[5]
    node_id = c[4].hex()
    print(f"Token: {addr}, Node ID: 0x{node_id}")
