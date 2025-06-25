# =========================================
# main.py 2025-06-25  full version (JST)
#  ・data/*.csv を読み込んでスコア計算
#  ・Code / Name 辞書から社名を付与
#  ・内訳を日本語ラベル
#  ・Slack 送信時にレスポンスを出力 & 失敗でジョブを赤く
# =========================================
import os, glob, pandas as pd, ta, requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ── 環境変数 ───────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")  # Settings → Secrets に登録
PRICE_DIR = "data"          # update_db.py が保存した CSV フォルダ
CSV_LIST  = "jpx_prime.csv" # Code,Name のヘッダー
PLIME_BONUS = 5             # プライム加点

# ── 銘柄コード → 社名 辞書 ──────────────────
df_list = pd.read_csv(CSV_LIST, dtype=str)
code2name = dict(zip(df_list["Code"].str.zfill(4), df_list["Name"]))

# ── 日本語ラベル変換 ────────────────────────
LABEL = {
    "GC"  : "ゴールデンクロス",
    "MACD": "MACD",
    "Vol" : "出来高",
    "RSI" : "RSI",
    "BB"  : "BB下限割れ",
    "High": "7日高値更新",
    "Low" : "7日安値割れ",
    "Mkt" : "市場加点",
}

# ── 1 銘柄のスコア計算 ───────────────────────
def score_one(df: pd.DataFrame, code: str) -> dict:
    s, p = df.iloc[-1], df.iloc[-2]          # 最新 & 1 本前
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
        score += 5; rs.append("High+5")
    if s["close"] < df["close"][-7:].min():
        score -= 10; rs.append("Low-10")

    score += PLIME_BONUS; rs.append(f"Mkt+{PLIME_BONUS}")
    jp_rs = [LABEL[r.split('+')[0]] + f"（{r.split('+')[1]}）" for r in rs]

    return {
        "code":   code,
        "name":   code2name.get(code, ""),
        "score":  score,
        "reasons": jp_rs,
    }

# ── メイン処理 ──────────────────────────────
def run():
    recs = []
    for path in sorted(glob.glob(f"{PRICE_DIR}/*.csv")):
        code = os.path.basename(path).split('.')[0]

        df = pd.read_csv(path)
        # 列名を小文字化し数値化
        df.columns = [c.lower().replace(' ', '_') for c in df.columns]
        df["close"]  = pd.to_numeric(df["close"],  errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df = df.dropna(subset=["close", "volume"])
        if len(df) < 25:
            continue

        df["sma5"]  = df["close"].rolling(5).mean()
        df["sma25"] = df["close"].rolling(25).mean()
        macd = ta.trend.MACD(df["close"])
        df["macd"], df["macd_s"] = macd.macd(), macd.macd_signal()
        df["rsi"]  = ta.momentum.RSIIndicator(df["close"]).rsi()
        bb         = ta.volatility.BollingerBands(df["close"])
        df["bb_l"] = bb.bollinger_lband()

        recs.append(score_one(df, code))

    top5 = sorted(recs, key=lambda x: x["score"], reverse=True)[:5]
    now  = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%m/%d %H:%M")

    msg = f"📈【買い候補 TOP5】({now})\n"
    for i, r in enumerate(top5, 1):
        msg += f"{i}. {r['code']} {r['name']} ▶ {r['score']}\n   └ " \
               + "｜".join(r['reasons']) + "\n"

    msg += "\n📉【売却候補】\n該当なし"

    # Slack 送信 & レスポンス表示
    if not SLACK_WEBHOOK_URL:
        print("❌ SLACK_WEBHOOK_URL が空です"); return

    resp = requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
    print("Slack response:", resp.status_code, resp.text[:120])
    resp.raise_for_status()  # 200 以外ならジョブをエラーにする

# 実行
if __name__ == "__main__":
    run()
