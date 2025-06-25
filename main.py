# 🚀 試運転版・株価予測Bot v1.9  （プライム限定CSV・JST表示・to_seriesで1次元化・必ずTOP5）

import os, pandas as pd, yfinance as yf, ta, requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ────── 設定 ──────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")          # GitHub Secrets
my_holdings = ["2503", "4661", "5411", "8233", "8304"]      # 特定口座

# ────── 銘柄リスト（プライムCSV）──────
df = pd.read_csv("jpx_prime.csv", dtype=str)
df = df.rename(columns={"コード": "Code", "市場・商品区分": "Market"})
df["Code"] = df["Code"].str.zfill(4)

tickers = {code: "プライム" for code in df["Code"]}         # 全銘柄プライム扱い
def get_market_score(_): return 5                           # 固定+5

# ────── ヘルパー ──────
def to_series(col):
    """Close/Volume が DataFrame や ndarray でも 1 次元 Series へ強制変換"""
    if isinstance(col, pd.DataFrame):
        return col.iloc[:, 0]
    return pd.Series(col)

# ────── 株価解析 ──────
def analyze_stock(symbol: str):
    try:
        dfp = yf.download(f"{symbol}.T", period="3mo", interval="1d",
                          auto_adjust=False, progress=False)
        if dfp.empty or len(dfp) < 30:
            return None

        dfp["Close"], dfp["Volume"] = to_series(dfp["Close"]), to_series(dfp["Volume"])
        dfp[["Close", "Volume"]] = dfp[["Close", "Volume"]].ffill()

        # 指標
        dfp["sma5"]  = dfp["Close"].rolling(5).mean()
        dfp["sma25"] = dfp["Close"].rolling(25).mean()
        macd = ta.trend.MACD(dfp["Close"])
        dfp["macd"], dfp["macd_signal"] = macd.macd(), macd.macd_signal()
        dfp["rsi"]   = ta.momentum.RSIIndicator(dfp["Close"]).rsi()
        bb           = ta.volatility.BollingerBands(dfp["Close"])
        dfp["bb_low"]= bb.bollinger_lband()

        latest, prev = dfp.iloc[-1], dfp.iloc[-2]
        score, reasons = 0, []

        # GC
        if prev["sma5"] < prev["sma25"] and latest["sma5"] > latest["sma25"]:
            pts = round(min(max((latest["sma5"]-latest["sma25"])/latest["sma25"],0),0.05)*300)
            score += pts; reasons.append(f"GC(+{pts})")
        # MACD
        if prev["macd"] < prev["macd_signal"] and latest["macd"] > latest["macd_signal"]:
            pts = round(min(max(latest["macd"]-latest["macd_signal"],0),0.5)*30)
            score += pts; reasons.append(f"MACD(+{pts})")
        # Volume
        if latest["Volume"] > prev["Volume"]:
            rate = latest["Volume"]/prev["Volume"]; pts = round(min((rate-1)*20,10))
            score += pts; reasons.append(f"出来高(+{pts})")
        # RSI
        if latest["rsi"] < 30:
            pts = 10 if latest["rsi"] < 20 else 5
            score += pts; reasons.append(f"RSI(+{pts})")
        # BB
        if latest["Close"] < latest["bb_low"]:
            pts = round(min((latest["bb_low"]-latest["Close"])/latest["bb_low"],0.03)*300)
            score += pts; reasons.append(f"BB下限(+{pts})")
        # 高値/安値
        if latest["Close"] > dfp["Close"][-7:].max():
            score += 5; reasons.append("高値(+5)")
        if latest["Close"] < dfp["Close"][-7:].min():
            score -= 10; reasons.append("安値割れ(-10)")

        return {"symbol": symbol, "score": score, "reasons": reasons}

    except Exception as e:
        # エラー銘柄もスコア0で残す → 必ずTOP5埋まる
        return {"symbol": symbol, "score": 0, "reasons": [f"解析エラー:{e}"]}

# ────── Slack ──────
def send_slack(text):
    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json={"text": text})

# ────── コメント ──────
def comment(scores):
    if not scores: return "データ不足で判定不能。"
    avg = sum(scores)/len(scores)
    if avg >= 70: return "今日は買い候補が強いです。複数銘柄の検討を。"
    if avg >= 50: return "中程度のシグナルが見られます。選別判断を。"
    if avg >= 30: return "弱め中心。慎重に。"
    return "全体的に低調です。見送りも視野に。"

# ────── メイン ──────
def run():
    buy, sell, scores = [], [], []

    for code, market in tickers.items():
        res = analyze_stock(code)
        res["score"] += get_market_score(market)
        res["reasons"].append("市場(プライム:+5)")
        buy.append(res); scores.append(res["score"])

    for code in my_holdings:
        res = analyze_stock(code)
        if res["score"] < 0:
            sell.append(res)

    # 強制TOP5
    top5 = sorted(buy, key=lambda x: x["score"], reverse=True)[:5]

    now  = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%m/%d %H:%M")
    msg  = f"📈【買い候補 TOP5】({now})\n"
    for i, r in enumerate(top5, 1):
        msg += f"{i}. {r['symbol']} ▶ {r['score']}\n　→ {'／'.join(r['reasons'][:4])}\n"

    msg += "\n📉【売却候補（保有銘柄）】\n"
    msg += "\n".join([f"- {r['symbol']} ▶ {r['score']} → {'／'.join(r['reasons'][:3])}" for r in sell]) or "該当なし"
    msg += f"\n\n🗨️ちゃちゃのひと言：\n{comment(scores)}"

    send_slack(msg)

# ────── 実行 ──────
if __name__ == "__main__":
    run()
