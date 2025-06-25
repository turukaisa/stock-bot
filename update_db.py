# update_db.py  ─ 確実版（CSV保存・必要列のみ・依存ゼロ）

import pandas as pd
import yfinance as yf
import os, time

CSV_LIST = "jpx_prime.csv"     # 銘柄リスト
DATA_DIR = "data"              # 保存フォルダ
PERIOD   = "3mo"               # 3か月分
WAIT_S   = 1                   # 連続DLの間隔（秒）

os.makedirs(DATA_DIR, exist_ok=True)

codes = (
    pd.read_csv(CSV_LIST, dtype=str)["コード"]
      .str.zfill(4)
      .tolist()
)

for code in codes:
    fn = f"{DATA_DIR}/{code}.csv"
    if os.path.exists(fn):
        print(f"✅ {code} 既に取得済み")
        continue

    print(f"📥 {code}.T ダウンロード中...")
    try:
        df = yf.download(f"{code}.T", period=PERIOD, interval="1d", progress=False)
        if df.empty:
            print(f"⚠️ {code} データなし")
            continue

        df = df.reset_index()[["Date", "Open", "High", "Low", "Close", "Volume"]]
        df.columns = ["date", "open", "high", "low", "close", "volume"]
        df.to_csv(fn, index=False)
        print(f"📦 {code} 保存完了 ({len(df)} 行)")
        time.sleep(WAIT_S)
    except Exception as e:
        print(f"❌ {code} 取得失敗: {e}")
