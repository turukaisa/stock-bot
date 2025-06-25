# update_db.py（全銘柄の株価をまとめて保存）
import pandas as pd
import yfinance as yf
import os

os.makedirs("data", exist_ok=True)

df = pd.read_csv("jpx_prime.csv", dtype=str)
codes = df["コード"].str.zfill(4).tolist()

all_data = []

for code in codes:
    try:
        symbol = f"{code}.T"
        print(f"📥 {symbol} ダウンロード中...")
        df_price = yf.download(symbol, period="3mo", interval="1d", progress=False)
        if df_price.empty:
            print(f"⚠️ {code} → データなし")
            continue
        df_price = df_price.reset_index()
        df_price["code"] = code
        all_data.append(df_price)
    except Exception as e:
        print(f"❌ {code} → エラー: {e}")

if all_data:
    df_all = pd.concat(all_data)
    df_all.columns = ["date", "open", "high", "low", "close", "adj_close", "volume", "code"]
    df_all.to_parquet("data/price.parquet", index=False)
    print("✅ 保存完了：data/price.parquet")
else:
    print("⚠️ 有効なデータがありませんでした")
