from web3 import Web3
from app.config import get_settings
from app.chain.contracts import get_contract
import json

settings = get_settings()
w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
oracle = get_contract(w3, settings.addresses.oracle_manager, "oracle_manager")
node_id = "0x066ef68c9d9ca51eee861aeb5bce51a12e61f06f10bf62243c563671ae3a9733"
try:
    node = oracle.functions.getNode(node_id).call()
    print(f"Node Type: {node[0]}")
    print(f"Parameters: {node[1].hex()}")
    print(f"Parents: {node[2]}")
except Exception as e:
    print(f"Error: {e}")
