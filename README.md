# HyperEVM HyperCore Indexer

A [HyperIndex](https://docs.envio.dev/docs/HyperIndex/overview) indexer for everything
[HyperEVM](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/hyperevm) (chain ID `999`)
sends to HyperCore, exposed as GraphQL.

It indexes the three ways value and instructions leave HyperEVM for HyperCore:

- `RawAction` logs from the CoreWriter system contract at `0x3333333333333333333333333333333333333333`,
  decoded into Hyperliquid's documented action IDs
- `Received` logs from the HYPE system address at `0x2222222222222222222222222222222222222222`
- `Transfer` logs into a spot token's system address, `0x20` followed by its HyperCore token index,
  kept only when the sending contract is the one HyperCore links to that index

Transfers in the other direction, from HyperCore into HyperEVM, arrive as system transactions and do
not appear in HyperEVM's logs, so they are out of scope.

## Requirements

- Node.js 22 or newer
- Docker running
- An Envio API token from https://envio.dev/app/api-tokens

## Run it

```bash
pnpm install
cp .env.example .env   # then put your token in .env
pnpm codegen
pnpm dev
```

A GraphQL playground opens on http://localhost:8080. The local admin secret is `testing`.

## Entities

| Entity | What it holds |
| --- | --- |
| `CoreActionType` | Count, distinct senders and first and last block per CoreWriter action ID |
| `CoreWriterSender` | Actions sent per address |
| `SenderAction` | Actions per address per action ID |
| `HypeSender` | HYPE sent to HyperCore per address |
| `SpotTokenToCore` | Transfers, raw amount and distinct senders per linked spot token |
| `SpotSender` | Transfers per address per spot token |
| `DailyBoundaryStat` | Daily counts across all three |
| `BoundaryTotal` | Running totals, including payloads that are not version 1 and transfers to a system address from an unlinked contract |

## Notes

- HyperSync is the default data source for chain `999`, so no RPC is configured.
- Which ERC-20 contract is linked to each HyperCore token index comes from Hyperliquid's
  [`spotMeta` info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/spot),
  read through the [Effect API](https://docs.envio.dev/docs/HyperIndex/effect-api) and cached.
- `scripts/system_txs.py` compares the official RPC's system transactions with what HyperSync returns
  for a fixed block window. It reads `ENVIO_API_TOKEN` from the environment.
