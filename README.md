# ETH ETFフロー × ステーキング

Ethereum ETFの日次純流入と、Ethereumステーキングの日次純流入（入金 − 引き出し）を同じ日付で並べて見るページです。

- 公開ページ: https://mitsuhitokawada.github.io/eth-etf-staking/
- データ: `data/`（Farside Investors の ETF フロー、Dune の hildobby 集計によるステーキングフロー）
- 生成: `python3 build.py` で `docs/data.js` と `docs/data.json` を作り直します
- 公開: `main` に push すると GitHub Actions が `docs/` を GitHub Pages に配信します
