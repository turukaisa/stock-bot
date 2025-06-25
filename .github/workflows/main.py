import os, pandas as pd, ta, requests
from datetime import datetime
from zoneinfo import ZoneInfo

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
PLIME_BONUS = 5
HOLDINGS = ["2503", "4661", "5411", "8233", "8304"]

def load_data(code):
    path = f"data/{code}.csv"
    if not os.path.exists(path): return None
    df = pd.read_csv(path, parse_dates=["Date"])
    if len(df) < 30: return None
    return df.tail(64).copy()

def analyze(code):
    try:
        df = load_data(code)
        if df is None: raise ValueError("no data")

        df["sma5"] = df["Close"].rolling(5).mean()
        df["sma25"] = df["Close"].rolling(25).mean()
        macd = ta.trend.MACD(df["Close"])
        df["macd"], df["macd_s"] = macd.macd(), macd.macd_signal()
        rsi = ta.momentum.RSIIndicator(df["Close"]).rsi()
        bb = ta.volatility.BollingerBands(df["Close"])
        df["rsi"], df["bb_l"] = rsi, bb.bollinger_lband()

        latest, prev = df.iloc[-1], df.iloc[-2]
        score, rs = 0, []

        if prev["sma5"] < prev["sma25"] and latest["sma5"] > latest["sma25"]:
            pts = round(min(max((latest["sma5"]-latest["sma25"])/latest["sma25"],0),0.05)*300)
            score += pts; rs.append(f"GC+{pts}")
        if prev["macd"] < prev["macd_s"] and latest["macd"] > latest["macd_s"]:
            pts = round(min(max(latest["macd"]-latest["macd_s"],0),0.5)*30)
            score += pts; rs.append(f"MACD+{pts}")
        if latest["Volume"] > prev["Volume"]:
            rate = latest["Volume"]/prev["Volume"]
            pts = round(min((rate-1)*40,20))
            score += pts; rs.append(f"Vol+{pts}")
        if latest["rsi"] < 40:
            pts = 10 if latest["rsi"] < 30 else 5
            score += pts; rs.append(f"RSI+{pts}")
        if latest["Close"] < df["bb_l"].iloc[-1]:
            pts = round(min((df["bb_l"].iloc[-1]-latest["Close"])/df["bb_l"].iloc[-1],0.03)*300)
            score += pts; rs.append(f"BB+{pts}")
        if latest["Close"] > df["Close"][-7:].max():
            score += 5; rs.append("High+5")
        if latest["Close"] < df["Close"][-7:].min():
            score -= 10; rs.append("Low-10")

        score += PLIME_BONUS
        rs.append(f"Market+{PLIME_BONUS}")

        return {"code": code, "score": score, "reasons": rs}
    except Exception as e:
        return {"code": code, "score": 0, "reasons": [f"ERR:{e.__class__.__name__}"]}

def send_slack(text):
    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json={"text": text})

def run():
    df = pd.read_csv("jpx_prime.csv", dtype=str)
    df["コード"] = df["コード"].str.zfill(4)
    codes = df["コード"].tolist()

    buy, sell, scores = [], [], []

    for code in codes:
        res = analyze(code)
        buy.append(res)
        scores.append(res["score"])

    for code in HOLDINGS:
        res = analyze(code)
        if res["score"] < 0:
            sell.append(res)

    top5 = sorted(buy, key=lambda x: x["score"], reverse=True)[:5]
    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%m/%d %H:%M")
    msg = f"📈【買い候補 TOP5】({now})\n"
    for i, r in enumerate(top5, 1):
        msg += f"{i}. {r['code']} ▶ {r['score']}\n　→ {'／'.join(r['reasons'][:3])}\n"

    msg += "\n📉【売却候補（保有銘柄）】\n"
    msg += "\n".join(
        f"- {r['code']} ▶ {r['score']} → {'／'.join(r['reasons'][:3])}"
        for r in sell
    ) or "該当なし"

    send_slack(msg)

if __name__ == "__main__":
    run()
