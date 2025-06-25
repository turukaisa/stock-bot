# ✅ 株価予測Bot v1.7   （プライム限定CSV・JST表示・ログ強化・安定化）

import os
import pandas as pd
import yfinance as yf
import ta
import requests
from datetime import datetime
from zoneinfo import ZoneInfo   # Python 3.9+

# ─────────────────────────────
# 1️⃣ 環境・定数
# ─────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")   # GitHub Secrets に登録

# 保有銘柄（売却監視用）─ 特定口座分
my_holdings = ["2503", "4661", "5411", "8233", "8304"]

# ─────────────────────────────
# 2️⃣ 銘柄リスト（プライム限定 CSV）
#     CSV ヘッダー: 日付,コード,銘柄名,市場・商品区分, …
# ─────────────────────────────
df = pd.read_csv("jpx_prime.csv", dtype=str)
df = df.rename(columns={"コード": "Code", "市場・商品区分": "Market"})
df["Code"] = df["Code"].str.zfill(4)           # 4 桁ゼロ埋め

# CSVがすでにプライム限定なので Market は固定でOK
tickers = {code: "プライム" for code in df["Code"]}

def get_market_score(_):      # すべてプライム
    return 5

# ─────────────────────────────
# 3️⃣ 株価分析関数
# ─────────────────────────────
def analyze_stock(symbol: str):
    try:
        dfp = yf.download(
            f"{symbol}.T",
            period="3mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
        )

        if dfp.empty or len(dfp) < 30:
            print(f"⚠️ {symbol}: データ不足 ({len(dfp)} 行)")
            return None

        # 欠損を前日値で補完（休日跨ぎ対応）
        dfp[["Close", "Volume"]] = dfp[["Close", "Volume"]].fillna(method="ffill")

        # ─ 指標計算
        dfp["sma5"]  = dfp["Close"].rolling(5).mean()
        dfp["sma25"] = dfp["Close"].rolling(25).mean()

        macd = ta.trend.MACD(dfp["Close"])
        dfp["macd"]        = macd.macd()
        dfp["macd_signal"] = macd.macd_signal()

        dfp["rsi"] = ta.momentum.RSIIndicator(dfp["Close"]).rsi()
        bb         = ta.volatility.BollingerBands(dfp["Close"])
        dfp["bb_low"] = bb.bollinger_lband()

        latest, prev = dfp.iloc[-1], dfp.iloc[-2]
        score, reasons = 0, []

        # ── 各スコア計算
        if prev["sma5"] < prev["sma25"] and latest["sma5"] > latest["sma25"]:
            pts = round(min(max((latest["sma5"]-latest["sma25"])/latest["sma25"],0),0.05)*300)
            score += pts; reasons.append(f"GC(+{pts})")

        if prev["macd"] < prev["macd_signal"] and latest["macd"] > latest["macd_signal"]:
            pts = round(min(max(latest["macd"]-latest["macd_signal"],0),0.5)*30)
            score += pts; reasons.append(f"MACD(+{pts})")

        if latest["Volume"] > prev["Volume"]:
            rate = latest["Volume"]/prev["Volume"]
            pts  = round(min((rate-1)*20,10))
            score += pts; reasons.append(f"出来高(+{pts})")

        if latest["rsi"] < 30:
            pts = 10 if latest["rsi"] < 20 else 5
            score += pts; reasons.append(f"RSI(+{pts})")

        if latest["Close"] < latest["bb_low"]:
            pts = round(min((latest["bb_low"]-latest["Close"])/latest["bb_low"],0.03)*300)
            score += pts; reasons.append(f"BB下限(+{pts})")

        if latest["Close"] > dfp["Close"][-7:].max():
            score += 5;  reasons.append("高値(+5)")
        if latest["Close"] < dfp["Close"][-7:].min():
            score -= 10; reasons.append("安値割れ(-10)")

        return {"symbol": symbol, "score": score, "reasons": reasons}

    except Exception as e:
        print(f"⚠️ 例外発生: {symbol} → {e}")
        return None

# ─────────────────────────────
# 4️⃣ Slack 送信
# ─────────────────────────────
def send_slack(text: str):
    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json={"text": text})
    else:
        print("⚠️ Slack Webhook URL 未設定")

# ─────────────────────────────
# 5️⃣ コメント生成
# ─────────────────────────────
def comment(scores: list[int]) -> str:
    avg = sum(scores)/len(scores) if scores else 0
    if avg >= 70: return "今日は買い候補が強いです。複数銘柄の検討を。"
    if avg >= 50: return "中程度のシグナルが多く見られます。選別判断を。"
    if avg >= 30: return "弱めのシグナルが中心。慎重に。"
    return "全体的に低調です。見送りも視野に。"

# ─────────────────────────────
# 6️⃣ メイン処理
# ─────────────────────────────
def run():
    buy_signals, sell_signals, buy_scores = [], [], []

    # ── 買い候補
    for code, market in tickers.items():
        res = analyze_stock(code)
        if res:
            res["score"] += get_market_score(market)
            res["reasons"].append(f"市場({market}:+5)")
            buy_signals.append(res)
            buy_scores.append(res["score"])

    # ── 売却監視（保有銘柄）
    for code in my_holdings:
        res = analyze_stock(code)
        if res and res["score"] < 0:
            sell_signals.append(res)

    # ── ログ
    print("👀 解析銘柄:", len(buy_signals))
    print("👀 最高スコア:", max(buy_scores) if buy_scores else "なし")

    # ── メッセージ生成
    top5 = sorted(buy_signals, key=lambda x: x["score"], reverse=True)[:5]
    now  = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%m/%d %H:%M")
    msg  = f"📈【買い候補 TOP5】({now})\n"

    for i, r in enumerate(top5, 1):
        msg += f"{i}. {r['symbol']} ▶ スコア：{r['score']}\n　→ {'／'.join(r['reasons'])}\n"

    msg += "\n📉【売却候補（保有銘柄）】\n"
    if sell_signals:
        for r in sell_signals:
            msg += f"- {r['symbol']} ▶ スコア：{r['score']} → {'／'.join(r['reasons'])}\n"
    else:
        msg += "該当なし\n"

    msg += f"\n🗨️ちゃちゃのひと言：\n{comment(buy_scores)}"
    send_slack(msg)

# ▶️ スクリプト実行
if __name__ == "__main__":
    run()
