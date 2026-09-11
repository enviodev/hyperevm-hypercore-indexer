import os, json, time, urllib.request

TOKEN = os.environ["ENVIO_API_TOKEN"]
RPC = "https://rpc.hyperliquid.xyz/evm"
HYPERSYNC = "https://hyperliquid.hypersync.xyz/query"

def post(url, body, headers={}):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

def rpc(method, *params):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)}
    return post(RPC, body)["result"]

START, END = 45_600_000, 45_600_200

# System transactions, from the official RPC's dedicated method
system, blocks_with = set(), 0
for number in range(START, END):
    txs = rpc("eth_getSystemTxsByBlockNumber", hex(number)) or []
    blocks_with += bool(txs)
    system.update(tx["hash"] for tx in txs)
    time.sleep(0.2)  # stay inside the public endpoint's rate limit

# Every transaction HyperSync returns for the same blocks
returned, block = set(), START
while block < END:
    d = post(
        HYPERSYNC,
        {
            "from_block": block,
            "to_block": END,
            "transactions": [{}],
            "field_selection": {"transaction": ["hash"]},
        },
        {"Authorization": f"Bearer {TOKEN}"},
    )
    for batch in d["data"]:
        returned.update(tx["hash"] for tx in batch.get("transactions", []))
    if d["next_block"] <= block:
        break
    block = d["next_block"]

print(f"{END - START} blocks, {blocks_with} with system transactions, "
      f"{len(system)} system transactions")
print(f"HyperSync returned {len(returned)} transactions, "
      f"{len(system & returned)} of them system transactions")
