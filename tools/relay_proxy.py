#!/usr/bin/env python3
# M5の上で動かす小さな「中継」サーバー。
# ブラウザは各リレーの公開APIを直接読めない（CORS）ので、代わりにこのサーバーが
# 7つのリレーに聞いて、重複を除いてまとめて返す。Pythonの標準機能だけで動く。
#
# 使い方:  python3 relay_proxy.py         （127.0.0.1:5090 で待ち受け）
# 確認:    curl "http://127.0.0.1:5090/relay/v1/data/bidtraces/builder_blocks_received?slot=<スロット番号>"
import json, time, urllib.request
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
cache = {}  # (kind, slot) -> (取得時刻, 結果, 読めたリレー名)

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
            seen.add(k); out.append(b)
    cache[key] = (now, out, ok)
    for k in [k for k in cache if now - cache[k][0] > 600]:
        del cache[k]
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
        self._send(200, {"ok": True, "message": "eth-etf-staking の中継サーバー", "relays": [n for n, _ in RELAYS]})

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print(f"中継サーバーを 127.0.0.1:{PORT} で待ち受け中")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
