import glob, os, pandas as pd, ta, requests
from datetime import datetime
from zoneinfo import ZoneInfo

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
BONUS = 5
HOLDINGS = ["2503","4661","5411","8233","8304"]

def score_one(path):
    code = os.path.basename(path).split(".")[0]
    df = pd.read_csv(path, parse_dates=["date"])
    # ▼ 不正CSVを弾く
    req_cols = {"open","high","low","close","volume"}
    if not req_cols.issubset(df.columns):
        print(f"⚠️ {code} 列不足 → スキップ"); return None
    # 数値化（文字列→NaN を除外）
    for col in req_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    if len(df) < 30: return None

    df["sma5"]  = df["close"].rolling(5).mean()
    df["sma25"] = df["close"].rolling(25).mean()
    macd = ta.trend.MACD(df["close"])
    df["macd"], df["macd_s"] = macd.macd(), macd.macd_signal()
    rsi = ta.momentum.RSIIndicator(df["close"]).rsi()
    bb  = ta.volatility.BollingerBands(df["close"])
    df["rsi"], df["bb_l"] = rsi, bb.bollinger_lband()

    latest, prev = df.iloc[-1], df.iloc[-2]
    score, rs = 0, []
    if prev["sma5"]<prev["sma25"] and latest["sma5"]>latest["sma25"]: score+=30; rs.append("GC+30")
    if prev["macd"]<prev["macd_s"] and latest["macd"]>latest["macd_s"]: score+=15; rs.append("MACD+15")
    if latest["volume"]>prev["volume"]: score+=10; rs.append("Vol+10")
    if latest["rsi"]<40: score+=5; rs.append("RSI+5")
    if latest["close"]<df["bb_l"].iloc[-1]: score+=15; rs.append("BB+15")
    score+=BONUS; rs.append(f"Market+{BONUS}")
    return {"code":code,"score":score,"reasons":rs}

def send(text):
    if SLACK_WEBHOOK_URL: requests.post(SLACK_WEBHOOK_URL,json={"text":text})

def run():
    buy=[]; sell=[]
    for p in glob.glob("data/*.csv"):
        r=score_one(p)
        if r: buy.append(r)
    for c in HOLDINGS:
        p=f"data/{c}.csv"
        if os.path.exists(p):
            r=score_one(p)
            if r and r["score"]<0: sell.append(r)
    top5=sorted(buy,key=lambda x:x["score"],reverse=True)[:5]
    now=datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%m/%d %H:%M")
    msg=f"📈【買い候補 TOP5】({now})\n"
    for i,r in enumerate(top5,1):
        msg+=f"{i}. {r['code']} ▶ {r['score']}  {'/'.join(r['reasons'][:3])}\n"
    msg+="\n📉【売却候補】\n"
    msg+="\n".join(f"- {r['code']} ▶ {r['score']}" for r in sell) or "該当なし"
    send(msg)

if __name__=="__main__":
    run()
