import json, time, urllib.request, urllib.error

RPC = "https://rpc.hyperliquid.xyz/evm"
TRANSFER = "0xa9059cbb"  # transfer(address,uint256)
HYPE_SYSTEM = "0x2222222222222222222222222222222222222222"

def rpc(method, *params):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)}
    for attempt in range(6):
        req = urllib.request.Request(
            RPC, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                reply = json.loads(r.read())
            if "result" in reply:
                return reply["result"]
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
        time.sleep(10 * (attempt + 1))  # the public RPC rate limits by IP
    raise RuntimeError("still rate limited after retries")

def describe(tx):
    """Turn one system transaction into a readable credit."""
    if tx["from"] == HYPE_SYSTEM:
        return f"HYPE {int(tx['value'], 16):,} wei to {tx['to']}"
    if tx["input"].startswith(TRANSFER):
        recipient = "0x" + tx["input"][34:74]
        amount = int(tx["input"][74:138], 16)
        return f"transfer of {amount:,} on {tx['to']} to {recipient}, sent by {tx['from']}"
    return f"call {tx['input'][:10]} on {tx['to']}, sent by {tx['from']}"

START, END = 45_600_053, 45_600_074

for number in range(START, END):
    for tx in rpc("eth_getSystemTxsByBlockNumber", hex(number)) or []:
        print(f"{number:,}  {describe(tx)}")
    time.sleep(0.65)  # the public RPC allows 100 requests a minute
