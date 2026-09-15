import os, json, time, urllib.request, urllib.error

TOKEN = os.environ["ENVIO_API_TOKEN"]
RPC = "https://rpc.hyperliquid.xyz/evm"
HYPERSYNC = "https://hyperliquid.hypersync.xyz/query"

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

def rpc(method, *params):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)}
    for attempt in range(6):
        reply = post(RPC, body)
        if "result" in reply:
            return reply["result"]
        time.sleep(10 * (attempt + 1))  # the public RPC rate limits by IP
    raise RuntimeError(f"RPC error: {reply.get('error')}")

START, END = 45_600_000, 45_600_200

# System transactions, from the official RPC's dedicated method
system, blocks_with = set(), 0
for number in range(START, END):
    txs = rpc("eth_getSystemTxsByBlockNumber", hex(number)) or []
    blocks_with += bool(txs)
    system.update(tx["hash"] for tx in txs)
    time.sleep(0.65)  # the public RPC allows 100 requests a minute

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
