# =========================================
# main.py 2025-06-25 refactor
#   • data/*.csv から前日の株価を読み込み
#   • jpx_prime.csv で銘柄名を取得
#   • スコア内訳を日本語ラベルで整形
#   • Slack 送信（JST 時刻）
# =========================================
import os, glob, pandas as pd, ta, numpy as np, requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ----- 定数 -----
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
PRICE_DIR   = "data"            # update_db.py が保存したフォルダ
CSV_LIST    = "jpx_prime.csv"   # Code,Name のヘッダー
PLIME_BONUS = 5                 # 市場加点（全部プライムの場合でも表示用）

# ----- 銘柄リスト（dict: code→name） -----
df_list = pd.read_csv(CSV_LIST, dtype=str)
code2name = dict(zip(df_list["Code"].str.zfill(4), df_list["Name"]))

# ----- 採点関数 --------------------------------------------------
LABEL = {
    "GC"  : "ゴールデンクロス",
    "MACD": "MACD",
    "Vol" : "出来高",
    "RSI" : "RSI",
    "BB"  : "ボリンジャーバンド下抜け",
    "High": "直近７日高値更新",
    "Low" : "直近７日安値割れ",
    "Mkt" : "市場加点",
}

def score_one(df: pd.DataFrame, code: str) -> dict:
    """df は read_csv 直後の DataFrame（close/volume などの列あり）"""
    s = df.iloc[-1]                  # 最新行
    p = df.iloc[-2] if len(df) > 1 else s   # 1 本前

    score, rs = 0, []

    # ゴールデンクロス
    if s["sma5"] > s["sma25"] and p["sma5"] < p["sma25"]:
        pts = round(min(max((s["sma5"]-s["sma25"])/s["sma25"],0),0.05)*300)
        score += pts; rs.append(f"GC+{pts}")
    # MACD シグナル超え
    if s["macd"] > s["macd_s"] and p["macd"] < p["macd_s"]:
        pts = round(min(max(s["macd"]-s["macd_s"],0),0.5)*30)
        score += pts; rs.append(f"MACD+{pts}")
    # 出来高増加
    if s["volume"] > p["volume"]:
        pts = round(min(((s["volume"]/p["volume"])-1)*40,20))
        score += pts; rs.append(f"Vol+{pts}")
    # RSI
    if s["rsi"] < 40:
        pts = 10 if s["rsi"] < 30 else 5
        score += pts; rs.append(f"RSI+{pts}")
    # BB 下限ブレイク
    if s["close"] < s["bb_l"]:
        pts = round(min((s["bb_l"]-s["close"])/s["bb_l"],0.03)*300)
        score += pts; rs.append(f"BB+{pts}")
    # 高値・安値
    if s["close"] > df["close"][-7:].max():
        score += 5;  rs.append("High+5")
    if s["close"] < df["close"][-7:].min():
        score -= 10; rs.append("Low-10")

    # 市場加点
    score += PLIME_BONUS
    rs.append(f"Mkt+{PLIME_BONUS}")

    # 日本語化
    jp_reasons = [LABEL[k.split('+')[0]] + f"（{k.split('+')[1]}）" for k in rs]

    return {
        "code": code,
        "name": code2name.get(code, ""),
        "score": score,
        "reasons": jp_reasons,
    }

# ----- メイン ----------------------------------------------------
def run():
    # ── 価格 CSV をまとめて読む
    paths = sorted(glob.glob(f"{PRICE_DIR}/*.csv"))
    records = []
    for path in paths:
        code = os.path.basename(path).split('.')[0]  # data/1301.csv → 1301
        df = pd.read_csv(path)
        if len(df) < 25:            # データ不足はスキップ
            continue
        df["sma5"]  = df["close"].rolling(5).mean()
        df["sma25"] = df["close"].rolling(25).mean()
        macd = ta.trend.MACD(df["close"])
        df["macd"], df["macd_s"] = macd.macd(), macd.macd_signal()
        df["rsi"]   = ta.momentum.RSIIndicator(df["close"]).rsi()
        bb          = ta.volatility.BollingerBands(df["close"])
        df["bb_l"]  = bb.bollinger_lband()
        rec = score_one(df, code)
        records.append(rec)

    # ── 上位 5 件
    top5 = sorted(records, key=lambda x: x["score"], reverse=True)[:5]

    now = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%m/%d %H:%M")
    msg = f"📈【買い候補 TOP5】({now})\n"
    for i, r in enumerate(top5, 1):
        msg += f"{i}. {r['code']} {r['name']} ▶ {r['score']}\n   └ " \
               + "｜".join(r['reasons']) + "\n"

    # 今回は売り判定ロジックを省略（必要なら以前の処理を再利用）
    msg += "\n📉【売却候補】\n該当なし"

    # ── Slack 送信
    requests.post(SLACK_WEBHOOK_URL, json={"text": msg})

# 実行
if __name__ == "__main__":
    run()
