import urllib.request, json, sys

rpc_url = "https://api.mainnet-beta.solana.com"

payload = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress",
    "params": ["TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", {"limit": 20}]
}).encode()
req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
sigs = json.loads(resp.read().decode())["result"]
print(f"Got {len(sigs)} sigs", file=sys.stderr)

found_transfer = False
for s in sigs:
    if found_transfer:
        break
    if s.get("err") is not None:
        continue
    sig = s["signature"]
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
    }).encode()
    req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        continue
    tx = json.loads(resp.read().decode())
    result = tx.get("result")
    if not result:
        continue

    meta = result.get("meta", {})
    pre = meta.get("preBalances", [])
    post = meta.get("postBalances", [])

    for block in meta.get("innerInstructions", []):
        if found_transfer:
            break
        for instr in block["instructions"]:
            parsed = instr.get("parsed", {})
            if not parsed:
                continue
            t = parsed.get("type", "")
            if t in ("transferChecked", "transfer", "mintTo", "burn"):
                info = parsed.get("info", {})
                print(f"\nType: {t}")
                print(f"  mint: {info.get('mint')}")
                print(f"  source: {info.get('source')}")
                print(f"  destination: {info.get('destination')}")
                ta = info.get("tokenAmount", info)
                print(f"  tokenAmount: {json.dumps(ta)}")
                amount_str = ta.get("amount", info.get("amount", "0"))
                decimals = ta.get("decimals", 6)
                ui_amount = ta.get("uiAmount", 0)
                print(f"  amount_str: {amount_str}")
                print(f"  decimals: {decimals}")
                print(f"  uiAmount: {ui_amount}")

                # balance changes
                changes = []
                for i, (p, q) in enumerate(zip(pre, post)):
                    if p != q:
                        changes.append((i, q - p))
                print(f"  SOL balance changes: {[(i, d/1e9) for i,d in changes]}")
                found_transfer = True
                break

if not found_transfer:
    print("No transfer found in 20 sigs", file=sys.stderr)
