#!/usr/bin/env python3
# M5の上で動かす小さな「中継」サーバー。
# ブラウザは各リレーの公開APIを直接読めない（CORS）ので、代わりにこのサーバーが
# 7つのリレーに聞いて、重複を除いてまとめて返す。Pythonの標準機能だけで動く。
#
# 使い方:  python3 relay_proxy.py         （127.0.0.1:5090 で待ち受け）
# 確認:    curl "http://127.0.0.1:5090/relay/v1/data/bidtraces/builder_blocks_received?slot=<スロット番号>"
import json, os, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = 5090
RELAYS = [
    ("ultrasound", "https://relay.ultrasound.money"),
    ("Flashbots", "https://boost-relay.flashbots.net"),
    ("Titan", "https://titanrelay.xyz"),
    ("bloXroute max-profit", "https://bloxroute.max-profit.blxrbdn.com"),
    ("bloXroute regulated", "https://bloxroute.regulated.blxrbdn.com"),
    ("Aestus", "https://aestus.live"),
    ("Agnostic", "https://agnostic-relay.net"),
]
KINDS = ("builder_blocks_received", "proposer_payload_delivered")
KEEP = ("slot", "builder_pubkey", "block_hash", "value", "timestamp_ms", "timestamp", "num_tx", "block_number")
cache = {}  # (kind, slot) -> (取得時刻, 結果, 読めたリレー名)

# ---- ビルダーの鍵 → 名前 を、同じマシンのノード（Beacon API）から覚える ----
# リレーの入札データには鍵しかない。勝ったブロックの extra_data に名前が入っているので、
# ブロックの block_hash と入札の block_hash を突き合わせて覚え、ファイルに残す。
BEACON = "http://127.0.0.1:5052"
NAMES_FILE = os.path.expanduser("~/relay_names.json")
names = {}
try:
    names = json.load(open(NAMES_FILE))
except Exception:
    pass
names_lock = threading.Lock()

def hex_to_text(h):
    try:
        b = bytes.fromhex(h[2:] if h.startswith("0x") else h)
        return "".join(chr(c) for c in b if 32 <= c < 127).strip()
    except Exception:
        return ""

def block_info(slot):
    """ノードから (block_hash, extra_data の文字列) を返す。空きスロットなら None"""
    try:
        req = urllib.request.Request(f"{BEACON}/eth/v2/beacon/blocks/{slot}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as r:
            p = json.load(r)["data"]["message"]["body"]["execution_payload"]
        return p["block_hash"], hex_to_text(p.get("extra_data", ""))
    except Exception:
        return None

def learn(slot, rows):
    """rows（入札 or 渡した記録）の中に、そのスロットのブロックと同じ block_hash があれば名前を覚える"""
    info = block_info(slot)
    if not info:
        return
    bh, name = info
    if not name:
        return
    for b in rows:
        if b.get("block_hash") == bh and b.get("builder_pubkey"):
            with names_lock:
                if names.get(b["builder_pubkey"]) != name:
                    names[b["builder_pubkey"]] = name
                    try:
                        json.dump(names, open(NAMES_FILE, "w"), indent=1)
                    except Exception:
                        pass
            return

def backfill():
    """起動時に、各リレーの「最近渡したブロック」200件ぶんの名前をまとめて覚える（1回だけ）"""
    time.sleep(3)
    for _, url in RELAYS:
        try:
            req = urllib.request.Request(f"{url}/relay/v1/data/bidtraces/proposer_payload_delivered?limit=200",
                                         headers={"Accept": "application/json", "User-Agent": "eth-etf-staking-race/1"})
            with urllib.request.urlopen(req, timeout=8) as r:
                rows = json.load(r)
        except Exception:
            continue
        for b in rows if isinstance(rows, list) else []:
            if b.get("builder_pubkey") in names:
                continue
            try:
                learn(int(b["slot"]), [b])
            except Exception:
                pass
            time.sleep(0.05)

def ask(relay, kind, slot):
    name, url = relay
    try:
        req = urllib.request.Request(f"{url}/relay/v1/data/bidtraces/{kind}?slot={slot}",
                                     headers={"Accept": "application/json", "User-Agent": "eth-etf-staking-race/1"})
        with urllib.request.urlopen(req, timeout=4) as r:
            rows = json.load(r)
        return name, rows if isinstance(rows, list) else []
    except Exception:
        return name, None

def collect(kind, slot):
    key = (kind, slot); now = time.time()
    c = cache.get(key)
    if c and now - c[0] < 60:
        return c[1], c[2]
    with ThreadPoolExecutor(len(RELAYS)) as ex:
        results = list(ex.map(lambda rl: ask(rl, kind, slot), RELAYS))
    seen, out, ok = set(), [], []
    for name, rows in results:
        if rows is None:
            continue
        ok.append(name)
        for b in rows:
            k = (b.get("builder_pubkey"), b.get("block_hash"))
            if k in seen:
                continue
            seen.add(k)
            # ページで使う項目だけ残して軽くする（生のままだと1スロット数MBになる）
            out.append({f: b.get(f) for f in KEEP if f in b})
    cache[key] = (now, out, ok)
    for k in [k for k in cache if now - cache[k][0] > 600]:
        del cache[k]
    threading.Thread(target=learn, args=(slot, out), daemon=True).start()
    return out, ok

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj, relays=""):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "X-Relays")
        self.send_header("X-Relays", relays.encode("ascii", "replace").decode())  # ヘッダはASCIIのみ
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        kind = next((k for k in KINDS if u.path.endswith(k)), None)
        if kind and q.get("slot", [""])[0].isdigit():
            out, ok = collect(kind, int(q["slot"][0]))
            return self._send(200, out, ",".join(ok))
        if u.path.endswith("/names"):
            with names_lock:
                return self._send(200, dict(names))
        self._send(200, {"ok": True, "message": "eth-etf-staking の中継サーバー", "relays": [n for n, _ in RELAYS]})

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print(f"中継サーバーを 127.0.0.1:{PORT} で待ち受け中（覚えている名前: {len(names)} 件）")
    threading.Thread(target=backfill, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
