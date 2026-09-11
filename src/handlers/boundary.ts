import { indexer, createEffect, S, type EvmOnEventContext } from "envio";

const CHAIN_ID = "999";
const DAY = 86_400;

// Action IDs from Hyperliquid's CoreWriter documentation.
const ACTION_NAMES: Record<number, string> = {
  1: "Limit order",
  2: "Vault transfer",
  3: "Token delegate",
  4: "Staking deposit",
  5: "Staking withdraw",
  6: "Spot send",
  7: "USD class transfer",
  8: "Finalize EVM contract",
  9: "Add API wallet",
  10: "Cancel order by oid",
  11: "Cancel order by cloid",
  12: "Approve builder fee",
  13: "Send asset",
  15: "Borrow lend operation",
  16: "Set abstraction",
  17: "Outcome operation",
};

// Every spot token has a system address on HyperEVM, 0x20 followed by the
// token's HyperCore index in big-endian. Sending a linked token there moves it
// to HyperCore. The range covers every index in use with room to grow.
const MAX_TOKEN_INDEX = 2_000;
const SYSTEM_ADDRESSES = Array.from(
  { length: MAX_TOKEN_INDEX },
  (_, index): `0x${string}` => `0x20${index.toString(16).padStart(38, "0")}`,
);

const tokenIndexOf = (address: string): number | undefined => {
  const lower = address.toLowerCase();
  if (!lower.startsWith("0x20")) return undefined;
  const index = parseInt(lower.slice(4), 16);
  return index < MAX_TOKEN_INDEX ? index : undefined;
};

type SpotMeta = {
  tokens: {
    index: number;
    name: string;
    evmContract: { address: string } | null;
  }[];
};

// One request serves every token, so share it across effect calls.
let spotMeta: Promise<SpotMeta> | undefined;
const loadSpotMeta = () =>
  (spotMeta ??= fetch("https://api.hyperliquid.xyz/info", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "spotMeta" }),
  }).then(async (res) => {
    if (!res.ok) {
      spotMeta = undefined;
      throw new Error(`spotMeta request failed with ${res.status}`);
    }
    return (await res.json()) as SpotMeta;
  }));

// Which ERC-20 contract HyperCore links to a token index, from Hyperliquid's
// spotMeta endpoint. Cached, so each index is looked up once per sync.
const getLinkedToken = createEffect(
  {
    name: "getLinkedToken",
    input: S.number,
    output: { name: S.string, contract: S.string },
    cache: true,
    rateLimit: { calls: 5, per: "second" },
  },
  async ({ input }) => {
    const token = (await loadSpotMeta()).tokens.find((t) => t.index === input);
    return {
      name: token?.name ?? "",
      contract: token?.evmContract?.address.toLowerCase() ?? "",
    };
  },
);

const getTotal = (context: EvmOnEventContext) =>
  context.BoundaryTotal.getOrCreate({
    id: CHAIN_ID,
    coreActions: 0,
    coreWriterSenders: 0,
    nonVersionOneActions: 0,
    hypeTransfers: 0,
    hypeAmount: 0n,
    hypeSenders: 0,
    spotTransfers: 0,
    unlinkedSystemTransfers: 0,
  });

const getDay = (context: EvmOnEventContext, timestamp: number) => {
  const day = Math.floor(timestamp / DAY);
  return context.DailyBoundaryStat.getOrCreate({
    id: `${day}`,
    day,
    coreActions: 0,
    hypeTransfers: 0,
    hypeAmount: 0n,
    spotTransfers: 0,
  });
};

// Actions sent to HyperCore. The first byte of data is the encoding version
// and the next three bytes are the action ID, big-endian.
indexer.onEvent(
  { contract: "CoreWriter", event: "RawAction" },
  async ({ event, context }) => {
    const { user, data } = event.params;
    // CoreWriter accepts any bytes, so a payload can be too short to decode.
    // Those count under action ID 0, which the encoding does not assign.
    const decodable = data.length >= 10;
    const version = decodable ? parseInt(data.slice(2, 4), 16) : 0;
    const actionId = decodable ? parseInt(data.slice(4, 10), 16) : 0;
    const block = event.block.number;

    const [total, day, type, sender, senderAction] = await Promise.all([
      getTotal(context),
      getDay(context, event.block.timestamp),
      context.CoreActionType.get(`${actionId}`),
      context.CoreWriterSender.get(user),
      context.SenderAction.get(`${user}-${actionId}`),
    ]);

    context.CoreActionType.set({
      id: `${actionId}`,
      actionId,
      name: ACTION_NAMES[actionId] ?? `Unknown (${actionId})`,
      count: (type?.count ?? 0) + 1,
      senders: (type?.senders ?? 0) + (senderAction ? 0 : 1),
      firstBlock: type?.firstBlock ?? block,
      lastBlock: block,
    });
    context.SenderAction.set({
      id: `${user}-${actionId}`,
      sender: user,
      actionId,
      count: (senderAction?.count ?? 0) + 1,
    });
    context.CoreWriterSender.set({
      id: user,
      actions: (sender?.actions ?? 0) + 1,
      firstBlock: sender?.firstBlock ?? block,
      lastBlock: block,
    });
    context.DailyBoundaryStat.set({ ...day, coreActions: day.coreActions + 1 });
    context.BoundaryTotal.set({
      ...total,
      coreActions: total.coreActions + 1,
      coreWriterSenders: total.coreWriterSenders + (sender ? 0 : 1),
      nonVersionOneActions: total.nonVersionOneActions + (version === 1 ? 0 : 1),
    });
  },
);

// HYPE sent from HyperEVM to HyperCore.
indexer.onEvent(
  { contract: "HypeSystem", event: "Received" },
  async ({ event, context }) => {
    const { user, amount } = event.params;

    const [total, day, sender] = await Promise.all([
      getTotal(context),
      getDay(context, event.block.timestamp),
      context.HypeSender.get(user),
    ]);

    context.HypeSender.set({
      id: user,
      transfers: (sender?.transfers ?? 0) + 1,
      amount: (sender?.amount ?? 0n) + amount,
    });
    context.DailyBoundaryStat.set({
      ...day,
      hypeTransfers: day.hypeTransfers + 1,
      hypeAmount: day.hypeAmount + amount,
    });
    context.BoundaryTotal.set({
      ...total,
      hypeTransfers: total.hypeTransfers + 1,
      hypeAmount: total.hypeAmount + amount,
      hypeSenders: total.hypeSenders + (sender ? 0 : 1),
    });
  },
);

// Spot tokens sent from HyperEVM to HyperCore. HyperSync filters server side
// to transfers into a system address, then the handler keeps only those from
// the contract HyperCore links to that token index.
indexer.onEvent(
  {
    contract: "SpotToken",
    event: "Transfer",
    wildcard: true,
    where: () => ({ params: [{ to: SYSTEM_ADDRESSES }] }),
  },
  async ({ event, context }) => {
    const { from, to, value } = event.params;
    const tokenIndex = tokenIndexOf(to);
    if (tokenIndex === undefined) return;

    const [linked, total, day, token, sender] = await Promise.all([
      context.effect(getLinkedToken, tokenIndex),
      getTotal(context),
      getDay(context, event.block.timestamp),
      context.SpotTokenToCore.get(`${tokenIndex}`),
      context.SpotSender.get(`${tokenIndex}-${from}`),
    ]);

    if (linked.contract !== event.srcAddress.toLowerCase()) {
      context.BoundaryTotal.set({
        ...total,
        unlinkedSystemTransfers: total.unlinkedSystemTransfers + 1,
      });
      return;
    }

    context.SpotSender.set({
      id: `${tokenIndex}-${from}`,
      tokenIndex,
      transfers: (sender?.transfers ?? 0) + 1,
    });
    context.SpotTokenToCore.set({
      id: `${tokenIndex}`,
      tokenIndex,
      name: linked.name,
      contract: event.srcAddress,
      transfers: (token?.transfers ?? 0) + 1,
      amount: (token?.amount ?? 0n) + value,
      senders: (token?.senders ?? 0) + (sender ? 0 : 1),
    });
    context.DailyBoundaryStat.set({ ...day, spotTransfers: day.spotTransfers + 1 });
    context.BoundaryTotal.set({ ...total, spotTransfers: total.spotTransfers + 1 });
  },
);
