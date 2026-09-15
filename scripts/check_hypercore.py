import json, time, urllib.request, urllib.error
from decimal import Decimal

RPC = "https://rpc.hyperliquid.xyz/evm"
INFO = "https://api.hyperliquid.xyz/info"
CORE_WRITER = "0x3333333333333333333333333333333333333333"
START, END = 45_995_091, 45_995_140  # 50 blocks, the documented limit for one public eth_getLogs request

def post(url, body):
    for attempt in range(6):
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                reply = json.loads(r.read())
            if not (isinstance(reply, dict) and "error" in reply):
                return reply
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
        time.sleep(10 * (attempt + 1))  # rate limited, wait and retry
    raise RuntimeError("still rate limited after retries")

def rpc(method, *params):
    return post(RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)})["result"]

def words(payload, count):
    """Split the ABI-encoded fields after the 4-byte header into 32-byte words."""
    return [int(payload[8 + 64 * i : 8 + 64 * (i + 1)], 16) for i in range(count)]

wei_decimals = {t["index"]: t["weiDecimals"] for t in post(INFO, {"type": "spotMeta"})["tokens"]}
logs = rpc("eth_getLogs", {"fromBlock": hex(START), "toBlock": hex(END), "address": CORE_WRITER})

for log in logs:
    data = log["data"][2:]
    payload = data[128 : 128 + int(data[64:128], 16) * 2]  # the bytes inside RawAction's data
    action_id = int(payload[2:8], 16)
    sender = "0x" + log["topics"][1][26:]
    block = int(log["blockNumber"], 16)

    if action_id == 1:  # Limit order, looked up on HyperCore by its client order ID
        asset, is_buy, limit_px, sz, _, _, cloid = words(payload, 7)
        if cloid == 0:
            print(f"{block:,}  limit order with no cloid, not checked")
            continue
        reply = post(INFO, {"type": "orderStatus", "user": sender, "oid": f"0x{cloid:032x}"})
        order = reply.get("order", {})
        coin = order.get("order", {}).get("coin", "?")
        print(f"{block:,}  limit order {coin} size {sz / 1e8} at {limit_px / 1e8}: {order.get('status', reply['status'])}")

    elif action_id == 13:  # Send asset, looked up in the sender's HyperCore ledger
        destination, _, _, _, token, wei = words(payload, 6)
        destination = f"0x{destination:040x}"
        amount = Decimal(wei) / 10 ** wei_decimals[token]
        ts = int(rpc("eth_getBlockByNumber", hex(block), False)["timestamp"], 16) * 1000
        ledger = post(
            INFO,
            {"type": "userNonFundingLedgerUpdates", "user": sender, "startTime": ts - 2000, "endTime": ts + 10000},
        )
        match = [
            e for e in ledger
            if e["delta"].get("destination") == destination and Decimal(e["delta"]["amount"]) == amount
        ]
        found = f"ledger send at {match[0]['time']}" if match else "no matching ledger entry"
        print(f"{block:,}  send asset {amount} of token {token} to {destination}: {found}")

    else:
        print(f"{block:,}  action {action_id}, not checked")
    time.sleep(1)  # stay well inside the info endpoint's weight limit
