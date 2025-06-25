# update_db.py  ─ 3か月分を銘柄ごとに CSV 保存
import pandas as pd, yfinance as yf, os, time

CSV_LIST = "jpx_prime.csv"
DATA_DIR = "data"
PERIOD   = "3mo"
WAIT_S   = 1

os.makedirs(DATA_DIR, exist_ok=True)

codes = pd.read_csv(CSV_LIST, dtype=str)["Code"].str.zfill(4).tolist()

for code in codes:
    fn = f"{DATA_DIR}/{code}.csv"
    if os.path.exists(fn):
        print(f"✅ {code} 取得済み")
        continue
    print(f"📥 {code}.T ダウンロード…")
    try:
        df = yf.download(f"{code}.T", period=PERIOD, interval="1d", progress=False)
        if df.empty:
            print(f"⚠️ {code} データなし");  continue
        df = (df.reset_index()[["Date","Open","High","Low","Close","Volume"]]
                 .rename(columns={
                     "Date":"date","Open":"open","High":"high",
                     "Low":"low","Close":"close","Volume":"volume"
                 }))
        df.to_csv(fn, index=False)
        print(f"📦 {code} 保存完了 ({len(df)} 行)")
        time.sleep(WAIT_S)
    except Exception as e:
        print(f"❌ {code} 失敗: {e}")
