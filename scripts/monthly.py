import json, urllib.request, collections, datetime

URL = "http://localhost:8080/v1/graphql"
QUERY = """
query Daily($offset: Int!) {
  DailyBoundaryStat(order_by: { day: asc }, limit: 500, offset: $offset) {
    day
    coreActions
    hypeTransfers
    spotTransfers
  }
}
"""

def fetch(offset):
    req = urllib.request.Request(
        URL,
        data=json.dumps({"query": QUERY, "variables": {"offset": offset}}).encode(),
        headers={"Content-Type": "application/json",
                 "x-hasura-admin-secret": "testing"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["data"]["DailyBoundaryStat"]

rows, offset = [], 0
while True:
    page = fetch(offset)
    rows += page
    if len(page) < 500:
        break
    offset += 500

months = collections.defaultdict(lambda: [0, 0, 0])
for row in rows:
    month = datetime.datetime.fromtimestamp(row["day"] * 86_400, datetime.timezone.utc)
    totals = months[month.strftime("%Y-%m")]
    totals[0] += row["coreActions"]
    totals[1] += row["hypeTransfers"]
    totals[2] += row["spotTransfers"]

print("month    core_actions  hype_to_core  spot_to_core")
for month, (core, hype, spot) in sorted(months.items()):
    print(f"{month}  {core:>12,}  {hype:>12,}  {spot:>12,}")
