# =========================================
# main.py 2025-06-25  fix : CSV数値化エラー解消
#   • data/*.csv を読むときに
#       – 列名をすべて小文字へ統一
#       – close / volume を数値化（to_numeric）
#   • それ以外は前回と同じ
# =========================================
import os, glob, pandas as pd, ta, numpy as np, requests
from datetime import datetime
from zoneinfo import ZoneInfo

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
PRICE_DIR   = "data"              # update_db.py が保存したフォルダ
CSV_LIST    = "jpx_prime.csv"     # Code,Name ヘッダー
PLIME_BONUS = 5

# ── 銘柄名辞書 ────────────────────────────
df_list = pd.read_csv(CSV_LIST, dtype=str)
code2name = dict(zip(df_list["Code"].str.zfill(4), df_list["Name"]))

LABEL = {
    "GC"  : "ゴールデンクロス", "MACD": "MACD",
    "Vol" : "出来高", "RSI" : "RSI",
    "BB"  : "BB下限割れ", "High": "7日高値更新",
    "Low" : "7日安値割れ", "Mkt": "市場加点",
}

# ───────────────────────────────
def score_one(df: pd.DataFrame, code: str) -> dict:
    s, p = df.iloc[-1], df.iloc[-2]          # 最新 / 1本前
    score, rs = 0, []

    if s["sma5"] > s["sma25"] and p["sma5"] < p["sma25"]:
        pts = round(min(max((s["sma5"]-s["sma25"])/s["sma25"],0),0.05)*300)
        score += pts; rs.append(f"GC+{pts}")
    if s["macd"] > s["macd_s"] and p["macd"] < p["macd_s"]:
        pts = round(min(max(s["macd"]-s["macd_s"],0),0.5)*30)
        score += pts; rs.append(f"MACD+{pts}")
    if s["volume"] > p["volume"]:
        pts = round(min(((s["volume"]/p["volume"])-1)*40,20))
        score += pts; rs.append(f"Vol+{pts}")
    if s["rsi"] < 40:
        pts = 10 if s["rsi"] < 30 else 5
        score += pts; rs.append(f"RSI+{pts}")
    if s["close"] < s["bb_l"]:
        pts = round(min((s["bb_l"]-s["close"])/s["bb_l"],0.03)*300)
        score += pts; rs.append(f"BB+{pts}")
    if s["close"] > df["close"][-7:].max():
        score += 5;  rs.append("High+5")
    if s["close"] < df["close"][-7:].min():
        score -= 10; rs.append("Low-10")

    score += PLIME_BONUS; rs.append(f"Mkt+{PLIME_BONUS}")

    jp_reasons = [LABEL[k.split('+')[0]] + f"（{k.split('+')[1]}）" for k in rs]
    return {"code": code, "name": code2name.get(code, ""),
            "score": score, "reasons": jp_reasons}

# ───────────────────────────────
def run():
    records = []
    for path in sorted(glob.glob(f"{PRICE_DIR}/*.csv")):
        code = os.path.basename(path).split('.')[0]

        df = pd.read_csv(path)
        # ↓★ ここが修正ポイント ★───────────────────
        df.columns = [c.lower().replace(' ','_') for c in df.columns]
        df["close"]   = pd.to_numeric(df["close"],   errors="coerce")
        df["volume"]  = pd.to_numeric(df["volume"],  errors="coerce")
        df = df.dropna(subset=["close","volume"])
        # ──────────────────────────────────────────────
        if len(df) < 25:            # データ不足
            continue

        df["sma5"]  = df["close"].rolling(5).mean()
        df["sma25"] = df["close"].rolling(25).mean()
        macd = ta.trend.MACD(df["close"]); df["macd"], df["macd_s"] = macd.macd(), macd.macd_signal()
        df["rsi"]   = ta.momentum.RSIIndicator(df["close"]).rsi()
        bb          = ta.volatility.BollingerBands(df["close"]); df["bb_l"] = bb.bollinger_lband()

        records.append(score_one(df, code))

    top5 = sorted(records, key=lambda x: x["score"], reverse=True)[:5]
    now  = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%m/%d %H:%M")

    msg = f"📈【買い候補 TOP5】({now})\n"
    for i,r in enumerate(top5,1):
        msg += f"{i}. {r['code']} {r['name']} ▶ {r['score']}\n   └ " \
               + "｜".join(r['reasons']) + "\n"

    msg += "\n📉【売却候補】\n該当なし"
    requests.post(SLACK_WEBHOOK_URL, json={"text": msg})

if __name__ == "__main__":
    run()
