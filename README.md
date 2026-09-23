# ETH ETFフロー × ステーキング

Ethereum ETFの日次純流入と、Ethereumステーキングの日次純流入（入金 − 引き出し）を同じ日付で並べて見るページです。

- 公開ページ: https://mitsuhitokawada.github.io/eth-etf-staking/
- データ: `data/`（Farside Investors の ETF フロー、Dune の hildobby 集計によるステーキングフロー）
- 生成: `python3 build.py` で `docs/data.js` と `docs/data.json` を作り直します
- 公開: `main` に push すると GitHub Actions が `docs/` を GitHub Pages に配信します

## ビルダー競り（race.html）の中継サーバー

ブラウザからはリレーの公開APIを直接読めない（CORS）ので、ノード側で `tools/relay_proxy.py` を動かし、Tailscale Serve で `/relay` として公開する。ページの「M5の中継URL」欄に `https://<ノードのtailnet名>/relay` を入れると本物の入札が流れる。

```
curl -O https://raw.githubusercontent.com/mitsuhitokawada/eth-etf-staking/main/tools/relay_proxy.py
mkdir -p ~/.config/systemd/user && curl -o ~/.config/systemd/user/relay-proxy.service https://raw.githubusercontent.com/mitsuhitokawada/eth-etf-staking/main/tools/relay-proxy.service
systemctl --user enable --now relay-proxy
tailscale serve --bg --set-path /relay http://127.0.0.1:5090
```
