# update_db.py（株価データを保存するシンプルなベース）
import yfinance as yf
import pandas as pd
from datetime import datetime
import os

# 保存先フォルダ（なければ作成）
os.makedirs("data", exist_ok=True)

# 銘柄コード（例として1301〜1305）
codes = ["1301", "1302", "1303", "1304", "1305"]

for code in codes:
    try:
        ticker = f"{code}.T"
        df = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False)
        if not df.empty:
            df.to_csv(f"data/{code}.csv")
            print(f"✅ {code} → {len(df)}件保存")
        else:
            print(f"⚠️ {code} → データなし")
    except Exception as e:
        print(f"❌ {code} → エラー: {e}")
