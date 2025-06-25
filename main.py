# =================================================
# 📈 株価予測 Bot – 完全版 2025-06-25 (JST)
#   • 東証プライム CSV 一括取得
#   • CSV クリーンアップで欠損・重複・文字列エラー除去 ←⭐️NEW
#   • yfinance 安定化（5 s タイムアウト・2 回リトライ）
#   • Close/Volume 1 次元化 & 欠損補完
#   • 失敗銘柄も 0 点登録で必ず TOP5
#   • Slack JST 表示
# =================================================

import os, time, requests, pandas as pd, yfinance as yf, ta
from datetime import datetime
from zoneinfo import ZoneInfo

# ────────── 環境変数 ──────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# ────────── 定数 ──────────
CSV_FILE   = "jpx_prime.csv"      # プライム銘柄 CSV
MIN_ROWS   = 30                   # ダウンロード最低行数
DL_TIMEOUT = 5                    # yfinance タイムアウト秒
RETRY      = 2                    # リトライ回数
PRIME_BONUS = 5                   # 市場加点
HOLDINGS   = ["2503", "4661", "5411", "8233", "8304"]   # 特定口座保有

# ────────── ユーティリティ ──────────
def _to_series(col):
    """DataFrame / ndarray → Series へ 1-dim 化"""
    if isinstance(col, pd.DataFrame):
        return col.iloc[:, 0]
    return pd.Series(col)

def _download(code: str):
    """yfinance ダウンロードを RETRY 回リトライ"""
    ticker = f"{code}.T"
    for _ in range(RETRY + 1):
        try:
            return yf.download(
                ticker, period="3mo", interval="1d",
                auto_adjust=False, progress=False, timeout=DL_TIMEOUT
            )
        except Exception:
            time.sleep(1)
    raise RuntimeError("download failed")

def send_slack(text: str):
    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json={"text": text})

# ────────── CSV 読み込み + クリーンアップ ──────────
df_codes = (
    pd.read_csv(CSV_FILE, dtype=str)
      .rename(columns={"コード": "Code"})
)

# ① 空白 / NaN / 4 桁以外を除外
df_codes = df_codes[df_codes["Code"].str.fullmatch(r"\d{4}", na=False)]
# ② 重複コードを 1 行に
df_codes = df_codes.drop_duplicates(subset="Code")

df_codes["Code"] = df_codes["Code"].str.zfill(4)
TICKERS = df_codes["Code"].tolist()

# ────────── 株価分析 ──────────
def analyze(code: str) -> dict:
    try:
        df = _download(code)
        if df.empty or len(df) < MIN_ROWS:
            raise ValueError("rows<MIN")

        df["Close"], df["Volume"] = _to_series(df["Close"]), _to_series(df["Volume"])
        df[["Close", "Volume"]]   = df[["Close", "Volume"]].ffill()

        # テクニカル指標
        df["sma5"]  = df["Close"].rolling(5).mean()
        df["sma25"] = df["Close"].rolling(25).mean()
        macd = ta.trend.MACD(df["Close"])
        df["macd"], df["macd_s"] = macd.macd(), macd.macd_signal()
        df["rsi"]   = ta.momentum.RSIIndicator(df["Close"]).rsi()
        bb          = ta.volatility.BollingerBands(df["Close"])
        df["bb_l"]  = bb.bollinger_lband()

        latest, prev = df.iloc[-1], df.iloc[-2]
        score, rs = 0, []

        #  GC
        if prev["sma5"] < prev["sma25"] and latest["sma5"] > latest["sma25"]:
            pts = round(min(max((latest["sma5"]-latest["sma25"])/latest["sma25"],0),0.05)*300)
            score += pts; rs.append(f"GC+{pts}")
        #  MACD
        if prev["macd"] < prev["macd_s"] and latest["macd"] > latest["macd_s"]:
            pts = round(min(max(latest["macd"]-latest["macd_s"],0),0.5)*30)
            score += pts; rs.append(f"MACD+{pts}")
        #  Volume
        if latest["Volume"] > prev["Volume"]:
            rate = latest["Volume"]/prev["Volume"]; pts = round(min((rate-1)*40,20))
            score += pts; rs.append(f"Vol+{pts}")
        #  RSI
        if latest["rsi"] < 40:
            pts = 10 if latest["rsi"] < 30 else 5
            score += pts; rs.append(f"RSI+{pts}")
        #  BB
        if latest["Close"] < df["bb_l"].iloc[-1]:
            pts = round(min((df["bb_l"].iloc[-1]-latest["Close"])/df["bb_l"].iloc[-1],0.03)*300)
            score += pts; rs.append(f"BB+{pts}")
        #  高値/安値
        if latest["Close"] > df["Close"][-7:].max():
            score += 5;  rs.append("High+5")
        if latest["Close"] < df["Close"][-7:].min():
            score -= 10; rs.append("Low-10")

        score += PRIME_BONUS
        rs.append(f"Market+{PRIME_BONUS}")

        return {"code": code, "score": score, "reasons": rs}

    except Exception as e:
        # 失敗は 0 点で残す
        return {"code": code, "score": 0, "reasons": [f"ERR:{type(e).__name__}"]}

# ────────── メイン ──────────
def run():
    buy, sell, scores = [], [], []

    for code in TICKERS:
        res = analyze(code)
        buy.append(res); scores.append(res["score"])

    for code in HOLDINGS:
        res = analyze(code)
        if res["score"] < 0:
            sell.append(res)

    top5 = sorted(buy, key=lambda x: x["score"], reverse=True)[:5]

    now  = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%m/%d %H:%M")
    msg  = f"📈【買い候補 TOP5】({now})\n"
    for i, r in enumerate(top5, 1):
        msg += f"{i}. {r['code']} ▶ {r['score']}\n　→ {'／'.join(r['reasons'][:4])}\n"

    msg += "\n📉【売却候補（保有銘柄）】\n"
    msg += "\n".join(
        f"- {r['code']} ▶ {r['score']} → {'／'.join(r['reasons'][:3])}"
        for r in sell
    ) or "該当なし"

    send_slack(msg)

# ────────── 実行 ──────────
if __name__ == "__main__":
    run()
