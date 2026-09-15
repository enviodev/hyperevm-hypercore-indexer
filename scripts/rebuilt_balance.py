import os, json, time, urllib.request, urllib.error

TOKEN = os.environ["ENVIO_API_TOKEN"]
HYPERSYNC = "https://hyperliquid.hypersync.xyz"
RPC = "https://rpc.hyperliquid.xyz/evm"

# USDUC, and an address it was credited to from HyperCore at block 45,600,053
CONTRACT = "0x61ef9543f8919bb06e374b3bb58a17725e34f9d9"
HOLDER = "0xd1b3aa51c16f3be6859b5f0811a08bc37d9c9665"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
HOLDER_TOPIC = "0x" + "0" * 24 + HOLDER[2:]

def post(url, body, headers={}):
    for attempt in range(6):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **headers},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            time.sleep(10 * (attempt + 1))  # rate limited, wait and retry
    raise RuntimeError("still rate limited after retries")

END = 45_628_968  # stop at the same block as the rest of the post, so the counts stay fixed

def total(topics):
    """Count and sum every matching Transfer log from genesis up to END."""
    amount, count, block = 0, 0, 0
    while block < END:
        d = post(
            f"{HYPERSYNC}/query",
            {
                "from_block": block,
                "to_block": END,
                "logs": [{"address": [CONTRACT], "topics": topics}],
                "field_selection": {"log": ["data"]},
            },
            {"Authorization": f"Bearer {TOKEN}"},
        )
        for batch in d["data"]:
            for log in batch.get("logs", []):
                amount += int(log["data"], 16)
                count += 1
        if d["next_block"] <= block:
            break
        block = d["next_block"]
    return count, amount

logs_in, received = total([[TRANSFER], [], [HOLDER_TOPIC]])
logs_out, sent = total([[TRANSFER], [HOLDER_TOPIC]])

call = {"to": CONTRACT, "data": "0x70a08231" + HOLDER_TOPIC[2:]}  # balanceOf
body = {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [call, "latest"]}
balance = int(post(RPC, body)["result"], 16)

print(f"Up to block {END - 1:,}")
print(f"Transfer logs received: {logs_in}, total {received:,}")
print(f"Transfer logs sent: {logs_out}, total {sent:,}")
print(f"Balance rebuilt from logs: {received - sent:,}")
print(f"balanceOf on the official RPC when run: {balance:,}")
