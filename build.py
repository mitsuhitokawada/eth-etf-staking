"""
ETH ETFの日次フローと、ETHステーキングの流入・流出を同じ日付でそろえて
docs/data.json に書き出すスクリプト。

使い方（Macのターミナルで、このフォルダに移動してから）:
    python3 build.py

入力:
    data/etf_flows.csv      ETFの日次フロー（Duneなどから書き出したCSV）
    data/staking_flows.csv  ステーキングの日次の流入・流出（同上）
出力:
    docs/data.json          docs/index.html が読み込むデータ
"""

import json
from pathlib import Path

import pandas as pd

# このファイルがある場所を基準にパスを決める（どこから実行しても動くように）
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DOCS = BASE / "docs"


def find_column(df: pd.DataFrame, candidates: list[str]) -> str:
    """列名の候補リストから、実際にある列を1つ探す（大文字小文字は無視）。"""
    lower = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in lower:
            return lower[name.lower()]
    raise KeyError(f"列が見つかりません。候補: {candidates} / 実際の列: {list(df.columns)}")


def load_daily(path: Path, value_candidates: list[str], out_name: str) -> pd.DataFrame:
    """CSVを読み、日付と1つの数値列だけの「1日1行」の表にする。"""
    df = pd.read_csv(path)
    date_col = find_column(df, ["day", "date", "time", "block_date", "period"])
    value_col = find_column(df, value_candidates)

    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], utc=True, errors="coerce").dt.tz_localize(None).dt.normalize(),
        out_name: pd.to_numeric(df[value_col], errors="coerce"),
    })
    out = out.dropna(subset=["date"])
    # 同じ日が複数行あれば合計する（銘柄ごとに分かれているCSVでも1日1行になる）
    return out.groupby("date", as_index=False)[out_name].sum()


def main() -> None:
    # DuneのETF CSVは「日付 × 発行体」の縦長。tvl列がその日・その発行体のフロー(ETH)なので、
    # 日ごとに全発行体を合計すると、その日のETF全体の純流入(ETH)になる
    etf = load_daily(
        DATA / "etf_flows.csv",
        value_candidates=["tvl", "net_flow", "netflow", "net flow", "flow", "daily_net_flow", "total"],
        out_name="etf_flow",
    )

    staking_path = DATA / "staking_flows.csv"
    if staking_path.exists():
        staking = load_daily(
            staking_path,
            value_candidates=["net_flow", "netflow", "net flow", "flow", "net", "deposits_minus_withdrawals"],
            out_name="staking_flow",
        )
        # 日付でくっつける（outer: どちらかにしかない日も残す）
        merged = pd.merge(etf, staking, on="date", how="outer").sort_values("date")
    else:
        print("data/staking_flows.csv がまだ無いので、ETFだけで書き出します")
        merged = etf.assign(staking_flow=float("nan")).sort_values("date")

    # ETFが始まった日（2024-07-23）より前は落として、期間をそろえる
    merged = merged[merged["date"] >= "2024-07-23"]

    DOCS.mkdir(exist_ok=True)
    records = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "etf_flow": None if pd.isna(e) else round(float(e), 2),
            "staking_flow": None if pd.isna(s) else round(float(s), 2),
        }
        for d, e, s in merged.itertuples(index=False)
    ]
    (DOCS / "data.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(records)} 日分を docs/data.json に書き出しました（{records[0]['date']} 〜 {records[-1]['date']}）")


if __name__ == "__main__":
    main()
