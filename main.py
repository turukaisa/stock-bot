# ✅ 株価予測Bot v1.7（東証プライム限定 + スコアTOP5必ず通知）

import yfinance as yf
import pandas as pd
import ta
import requests
from datetime import datetime

# 🔗 Slack Webhook URL（GitHub Secretsで渡す）
import os
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# 🧾 保有銘柄（売却監視）※特定口座分のみ
my_holdings = ['2503', '4661', '5411', '8233', '8304']

# 📥 プライム銘柄リスト（CSV同梱）
df_jpx = pd.read_csv("jpx_prime.csv", dtype=str)
tickers = {code: market for code, market in zip(df_jpx["Code"], df_jpx["Market"])}

# 🎁 市場加点（現状は全てプライム）
def get_market_score(market):
    return 5 if "プライム" in market else 0

# 📊 分析関数
def analyze_stock(symbol):
    try:
        df = yf.download(f"{symbol}.T", period="3mo", interval="1d")
        if df.empty or len(df) < 30:
            return None

        df['sma5'] = df['Close'].rolling(5).mean()
        df['sma25'] = df['Close'].rolling(25).mean()
        macd = ta.trend.MACD(df['Close'])
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['rsi'] = ta.momentum.RSIIndicator(df['Close']).rsi()
        bb = ta.volatility.BollingerBands(df['Close'])
        df['bb_low'] = bb.bollinger_lband()

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        score = 0
        reasons = []

        # ゴールデンクロス
        if prev['sma5'] < prev['sma25'] and latest['sma5'] > latest['sma25']:
            pts = round(min(max((latest['sma5'] - latest['sma25']) / latest['sma25'], 0), 0.05) * 300)
            score += pts
            reasons.append(f"GC(+{pts})")

        # MACDクロス
        if prev['macd'] < prev['macd_signal'] and latest['macd'] > latest['macd_signal']:
            pts = round(min(max(latest['macd'] - latest['macd_signal'], 0), 0.5) * 30)
            score += pts
            reasons.append(f"MACD(+{pts})")

        # 出来高上昇
        if latest['Volume'] > prev['Volume']:
            rate = latest['Volume'] / prev['Volume']
            pts = round(min((rate - 1) * 20, 10))
            score += pts
            reasons.append(f"出来高(+{pts})")

        # RSI低下（割安）
        if latest['rsi'] < 30:
            pts = 10 if latest['rsi'] < 20 else 5
            score += pts
            reasons.append(f"RSI(+{pts})")

        # ボリンジャーバンド下限より下（下げすぎ）
        if latest['Close'] < latest['bb_low']:
            pts = round(min((latest['bb_low'] - latest['Close']) / latest['bb_low'], 0.03) * 300)
            score += pts
            reasons.append(f"BB下限(+{pts})")

        # 高値更新
        if latest['Close'] > df['Close'][-7:].max():
            score += 5
            reasons.append("高値(+5)")

        # 安値割れ
        if latest['Close'] < df['Close'][-7:].min():
            score -= 10
            reasons.append("安値割れ(-10)")

        return {
            'symbol': symbol,
            'score': score,
            'reasons': reasons
        }
    except Exception as e:
        print(f"⚠️ 例外発生：{symbol} → {e}")
        return None

# 🔔 Slack送信
def send_slack(text):
    if SLACK_WEBHOOK_URL:
        requests.post(SLACK_WEBHOOK_URL, json={"text": text})
    else:
        print("⚠️ Slack URLが未設定です")

# 🗣️ コメント生成
def comment(scores):
    avg = sum(scores) / len(scores) if scores else 0
    if avg >= 70:
        return "今日は買い候補が強いです。複数銘柄の検討を。"
    elif avg >= 50:
        return "中程度のシグナルが多く見られます。選別判断を。"
    elif avg >= 30:
        return "弱めのシグナルが中心。慎重に。"
    else:
        return "全体的に低調です。見送りも視野に。"

# ✅ 実行
def run():
    buy_signals = []
    sell_signals = []
    buy_scores = []

    for code, market in tickers.items():
        res = analyze_stock(code)
        if res:
            res['score'] += get_market_score(market)
            res['reasons'].append(f"市場({market}:+{get_market_score(market)})")
            buy_signals.append(res)
            buy_scores.append(res['score'])

    for code in my_holdings:
        res = analyze_stock(code)
        if res and res['score'] < 0:
            sell_signals.append(res)

    # top5はスコアが低くても必ず出す
    top5 = sorted(buy_signals, key=lambda x: x['score'], reverse=True)[:5]
    now = datetime.now().strftime("%m/%d %H:%M")
    msg = f"📈【買い候補 TOP5】({now})\n"

    for i, r in enumerate(top5, 1):
        msg += f"{i}. {r['symbol']} ▶ スコア：{r['score']}\n　→ {'+'.join(r['reasons'])}\n"

    msg += "\n📉【売却候補（保有銘柄）】\n"
    if sell_signals:
        for r in sell_signals:
            msg += f"- {r['symbol']} ▶ スコア：{r['score']} → {'+'.join(r['reasons'])}\n"
    else:
        msg += "該当なし\n"

    msg += "\n🗨️ちゃちゃのひと言：\n" + comment(buy_scores)
    send_slack(msg)

# ▶️ 実行
run()
