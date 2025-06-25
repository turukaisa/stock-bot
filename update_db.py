# update_db.py  ─ 6 ヶ月ぶん取得して CSV 保存
import os, pandas as pd, yfinance as yf

os.makedirs("data", exist_ok=True)

codes = pd.read_csv("jpx_prime.csv", dtype=str)["Code"].str.zfill(4)

for code in codes:
    try:
        sym = f"{code}.T"
        df  = yf.download(sym, period="6mo", interval="1d",
                          auto_adjust=False, progress=False)
        if len(df) < 30:
            print(f"⚠️ {code} 行不足 {len(df)}")
            continue

        df = df.reset_index()[["Date","Open","High","Low","Close","Volume"]]
        df.to_csv(f"data/{code}.csv", index=False)
        print("✅", code, len(df))
    except Exception as e:
        print("❌", code, e)
