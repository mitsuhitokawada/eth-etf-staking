# data/

ここにCSVを置きます。

| ファイル名 | 中身 | 出どころ |
|---|---|---|
| `etf_flows.csv` | Ethereum ETF の日次フロー | Dune: hildobby / Ethereum ETF |
| `staking_flows.csv` | ETH ステーキングの日次の流入・流出 | Dune: hildobby / ETH Staking |

列名はスクリプト側でだいたい自動で見つけます（`day` / `date` と `net_flow` / `flow` など）。

## eth_stakers_snapshot.csv
Dune「ETH Stakers」（hildobby/eth2-staking）を2026-09-22にエクスポートしたもの。主体（entity）ごとの現在のステーキング残高・検証者数・シェア・直近1週/1月/半年の変化。756主体＋Unidentified。

## eth_staked_by_entity.csv
Dune「ETH Staked by Entity」（hildobby/eth2-staking）を2026-09-22にエクスポートしたもの。週次（2020-11-02〜2026-09-21、308週）× 31主体（Others 含む）の、その時点のステーキング残高（cum_deposited_eth）と検証者数（cum_validators）。
