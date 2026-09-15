import os, json, time, collections, urllib.request, urllib.error

TOKEN = os.environ["ENVIO_API_TOKEN"]
HYPERSYNC = "https://hyperliquid.hypersync.xyz/query"

WALLET = "0x6b9e773128f453f5c2c60935ee2de2cbc5390a24"  # linked to USDC in spotMeta
CORE_WRITER = "0x3333333333333333333333333333333333333333"
USDC_SYSTEM = "0x2000000000000000000000000000000000000000"  # token index 0
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SPOT_DEX = 2**32 - 1

START, END = 45_528_967, 45_628_967  # END is exclusive

def topic(address):
    return "0x" + "0" * 24 + address[2:]

def logs(selection, fields):
    out, block = [], START
    while block < END:
        req = urllib.request.Request(
            HYPERSYNC,
            data=json.dumps({
                "from_block": block,
                "to_block": END,
                "logs": [selection],
                "field_selection": {"log": fields},
            }).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {TOKEN}"},
        )
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    d = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                time.sleep(10 * (attempt + 1))  # rate limited, wait and retry
        else:
            raise RuntimeError("still rate limited after retries")
        for batch in d["data"]:
            out += batch.get("logs", [])
        if d["next_block"] <= block:
            break
        block = d["next_block"]
    return out

# CoreWriter actions the wallet sent
actions = logs({"address": [CORE_WRITER], "topics": [[], [topic(WALLET)]]}, ["data"])
ids, routes, tokens, recipients = (collections.Counter(), collections.Counter(),
                                   collections.Counter(), set())
for log in actions:
    data = log["data"][2:]
    length = int(data[64:128], 16)
    payload = data[128:128 + length * 2]
    action_id = int(payload[2:8], 16)
    ids[action_id] += 1
    if action_id != 13:  # Send asset
        continue
    words = [payload[8 + i * 64:8 + (i + 1) * 64] for i in range(6)]
    recipients.add(words[0][-40:])
    source, destination = int(words[2], 16), int(words[3], 16)
    routes[("spot" if source == SPOT_DEX else source,
            "spot" if destination == SPOT_DEX else destination)] += 1
    tokens[int(words[4], 16)] += 1

# Transfer logs the wallet itself emitted into the USDC system address
signals = logs({"address": [WALLET], "topics": [[TRANSFER], [], [topic(USDC_SYSTEM)]]}, ["topic1"])
forwarded = sum(1 for log in signals if log["topic1"][-40:] == WALLET[2:])

print(f"Blocks {START:,} to {END - 1:,}")
print(f"CoreWriter actions from the wallet: {len(actions):,}, by action ID {dict(ids)}")
print(f"Send asset routes (source dex, destination dex): {dict(routes)}")
print(f"Send asset token indexes: {dict(tokens)}, distinct recipients: {len(recipients):,}")
print(f"Transfer logs from the wallet into the USDC system address: {len(signals):,}, "
      f"{forwarded:,} of them sent from the wallet itself")
