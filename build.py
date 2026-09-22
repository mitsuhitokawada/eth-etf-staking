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

# ETFデータの出どころ（Farsideのファイルがあればそちらを優先する）
ETF_UNIT = "ETH"
ETF_SOURCE_NAME = "Dune / hildobby「Ethereum ETF」"
ETF_SOURCE_URL = "https://dune.com/hildobby/eth-etfs"


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


def load_staking(path: Path) -> pd.DataFrame:
    """Duneの「Ethereum Staking Flows」CSVを、1日1行の純流入(ETH)にする。

    CSVは「日付, flow_type, amount」の縦長で、flow_type は
    Deposits(入金, +) / Withdrawn Rewards(報酬の引き出し, -) / Withdrawn Principal(元本の引き出し, -) /
    Net Flow(直近2週間の合計。日次ではないので使わない) の4種類。
    """
    df = pd.read_csv(path)
    df = df[df["flow_type"] != "Net Flow"]
    date = pd.to_datetime(df["time"], utc=True, errors="coerce").dt.tz_localize(None).dt.normalize()
    out = pd.DataFrame({"date": date, "staking_flow": pd.to_numeric(df["amount"], errors="coerce")})
    # 入金と引き出し(マイナス)を同じ日で足すと、その日の純流入になる
    return out.dropna(subset=["date"]).groupby("date", as_index=False)["staking_flow"].sum()


FARSIDE_COLS = ["ETHA", "ETHB", "FETH", "ETHW", "TETH", "ETHV", "QETH", "EZET", "MSSE", "ETHE", "ETH", "Total"]


def load_farside(path: Path) -> pd.DataFrame:
    """Farsideの表をコピーしたテキスト（日付|値,値,...）を、1日1行の表にする。単位は百万ドル。"""

    def num(s: str):
        s = s.strip()
        if s == "-":
            return None
        neg = s.startswith("(")            # 括弧はマイナス
        v = float(s.strip("()").replace(",", ""))
        return -v if neg else v

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d, vals = line.split("|")
        rows.append([pd.to_datetime(d, format="%d %b %Y")] + [num(v) for v in vals.split(",")])
    df = pd.DataFrame(rows, columns=["date"] + FARSIDE_COLS)
    return pd.DataFrame({
        "date": df["date"],
        "etf_flow": df["Total"],       # 全ETFの合計（百万ドル）
        "etf_etha": df["ETHA"],        # BlackRock ETHA（ステーキングなし）
        "etf_ethb": df["ETHB"],        # ステーキング型（2026-03-11 から）
    })


def main() -> None:
    # DuneのETF CSVは「日付 × 発行体」の縦長。tvl列がその日・その発行体のフロー(ETH)なので、
    # 日ごとに全発行体を合計すると、その日のETF全体の純流入(ETH)になる
    global ETF_UNIT, ETF_SOURCE_NAME, ETF_SOURCE_URL
    farside_path = DATA / "farside_eth_etf_flows.txt"
    if farside_path.exists():
        etf = load_farside(farside_path)
        ETF_UNIT = "百万ドル"
        ETF_SOURCE_NAME = "Farside Investors「Ethereum ETF Flow – All Data」"
        ETF_SOURCE_URL = "https://farside.co.uk/ethereum-etf-flow-all-data/"
    else:
        etf = load_daily(
            DATA / "etf_flows.csv",
            value_candidates=["tvl", "net_flow", "netflow", "net flow", "flow", "daily_net_flow", "total"],
            out_name="etf_flow",
        )
        etf["etf_etha"] = float("nan")
        etf["etf_ethb"] = float("nan")

    staking_path = DATA / "staking_flows.csv"
    if staking_path.exists():
        staking = load_staking(staking_path)
        # 日付でくっつける（outer: どちらかにしかない日も残す）
        merged = pd.merge(etf, staking, on="date", how="outer").sort_values("date")
    else:
        print("data/staking_flows.csv がまだ無いので、ETFだけで書き出します")
        merged = etf.assign(staking_flow=float("nan")).sort_values("date")

    # ETFが始まった日（2024-07-23）より前は落として、期間をそろえる
    merged = merged[merged["date"] >= "2024-07-23"]

    DOCS.mkdir(exist_ok=True)
    def clean(v):
        return None if pd.isna(v) else round(float(v), 2)

    records = [
        {
            "date": r.date.strftime("%Y-%m-%d"),
            "etf_flow": clean(r.etf_flow),
            "etf_etha": clean(r.etf_etha),
            "etf_ethb": clean(r.etf_ethb),
            "staking_flow": clean(r.staking_flow),
        }
        for r in merged.itertuples(index=False)
    ]
    (DOCS / "data.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    # index.html をダブルクリックで開いても動くように、JSファイルとしても書き出す
    meta = {
        "etf_unit": ETF_UNIT,
        "stk_unit": "ETH",
        "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "sources": [
            {"name": "Ethereum ETF: " + ETF_SOURCE_NAME, "url": ETF_SOURCE_URL,
             "range": f"{etf['date'].min():%Y-%m-%d}〜{etf['date'].max():%Y-%m-%d}"},
            {"name": "ステーキング: Dune / hildobby「Ethereum Staking Flows」", "url": "https://dune.com/hildobby/eth2-staking",
             "range": f"{merged.dropna(subset=['staking_flow'])['date'].min():%Y-%m-%d}〜{merged.dropna(subset=['staking_flow'])['date'].max():%Y-%m-%d}"},
        ],
    }
    (DOCS / "data.js").write_text(
        "window.ETF_STAKING_DATA = " + json.dumps(records, ensure_ascii=False) + ";\n"
        + "window.ETF_STAKING_META = " + json.dumps(meta, ensure_ascii=False) + ";\n", encoding="utf-8"
    )
    print(f"{len(records)} 日分を docs/data.json に書き出しました（{records[0]['date']} 〜 {records[-1]['date']}）")


# 分類の日本語名（Duneの entity_category → 画面に出す言葉）
CATEGORY_JA = {
    "Liquid Staking": "リキッドステーキング",
    "Liquid Restaking": "リキッドリステーキング",
    "CEXs": "取引所",
    "Staking Pools": "ステーキング業者",
    "Solo Stakers": "個人（ソロ）",
    "Unidentified": "未特定",
    "Others": "その他",
}


def build_stakers() -> None:
    """主体（Lido、Binance…）ごとの週次残高を docs/who.js に書き出す"""
    ts_path = DATA / "eth_staked_by_entity.csv"
    snap_path = DATA / "eth_stakers_snapshot.csv"
    if not ts_path.exists():
        print("data/eth_staked_by_entity.csv が無いので who.js は作りません")
        return
    ts = pd.read_csv(ts_path)
    ts["time"] = pd.to_datetime(ts["time"]).dt.normalize()
    # 主体 → 分類（スナップショットから引く。無ければ「その他」）
    cat = {}
    if snap_path.exists():
        snap = pd.read_csv(snap_path)
        cat = dict(zip(snap["entity_just_name"], snap["entity_category"]))
    cat.setdefault("Unidentified", "Unidentified")
    cat.setdefault("Others", "Others")
    cat.setdefault("Solo Stakers", "Solo Stakers")

    weeks = sorted(ts["time"].unique())
    wide = ts.pivot_table(index="time", columns="depositor_entity", values="cum_deposited_eth", aggfunc="max").reindex(weeks)
    wide = wide.ffill().fillna(0.0)
    order = wide.iloc[-1].sort_values(ascending=False).index.tolist()
    entities = []
    for name in order:
        entities.append({
            "name": name,
            "category": cat.get(name, "Others"),
            "category_ja": CATEGORY_JA.get(cat.get(name, "Others"), "その他"),
            "series": [round(float(v)) for v in wide[name].tolist()],
        })
    out = {
        "weeks": [pd.Timestamp(w).strftime("%Y-%m-%d") for w in weeks],
        "entities": entities,
        "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "source": {"name": "Dune / hildobby「ETH Staked by Entity」", "url": "https://dune.com/hildobby/eth2-staking"},
    }
    (DOCS / "who.js").write_text("window.STAKERS_WEEKLY = " + json.dumps(out, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"{len(weeks)} 週 × {len(entities)} 主体を docs/who.js に書き出しました")


if __name__ == "__main__":
    main()
    build_stakers()
