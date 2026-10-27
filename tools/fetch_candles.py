#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bitget K 線抓取器 — 給排程讀的資料源  v1.0.1

在 GitHub Actions 上跑（那裡可以直接連 Bitget，不需要任何人按同意）。
抓下來的 K 線經過驗證後寫成 CSV，提交到 `data` 分支；Claude 的排程只要 git clone 就能讀。

用法：
  python3 tools/fetch_candles.py core   OUTDIR   # 5 個標的的 1D + 4H（每小時跑）
  python3 tools/fetch_candles.py weekly OUTDIR   # 16 支觀察名單的 1W（每週跑）

規則（全部來自實測踩過的坑）：
- 一律用 history-candles；candles 端點在 limit 大時會回錯區間且不報錯。
- 每個請求帶 `_=<毫秒>` 破 CDN 快取（Bitget CDN 會對特定 URL 供應過期資料）。
  另外仍做新鮮度檢查，過期就換 limit 重試。
- 只保留「已收盤」的 K：開盤時間 + 週期 <= 現在。
- 驗證：時間戳連續、open == 前一根 close（永續連續交易時恆成立）。
- 驗證沒過 → 不覆寫舊檔，只在 status.json 標記錯誤。寧可舊資料被標成過期，也不要寫進壞資料。
"""
import sys, os, json, time, urllib.request, urllib.error

BASE = "https://api.bitget.com/api/v2/mix/market/history-candles"
STEP = {"4H": 14_400_000, "1D": 86_400_000, "1W": 604_800_000}
# 新鮮度：最後一根「已收盤」K 的開盤時間距現在的上限
FRESH = {"4H": 2 * 14_400_000, "1D": 2 * 86_400_000, "1W": 2 * 604_800_000}

CORE = ["BTCUSDT", "ETHUSDT", "CLUSDT", "NATGASUSDT", "MUUSDT"]
CORE_NEED = {"1D": 420, "4H": 360}  # 日線 EMA200+斜率要 260；多抓留餘裕
WATCH = ["LTCUSDT", "LDOUSDT", "SUIUSDT", "AVAXUSDT", "DOTUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT",
         "ARBUSDT", "OPUSDT", "FILUSDT", "INJUSDT", "AAVEUSDT", "UNIUSDT", "CRVUSDT", "SEIUSDT"]
WATCH_NEED = {"1W": 80}


def now_ms():
    return int(time.time() * 1000)


def get(sym, gran, limit, end_time=None, tries=4):
    q = f"?symbol={sym}&productType=USDT-FUTURES&granularity={gran}&limit={limit}"
    if end_time is not None:
        q += f"&endTime={end_time}"
    last_err = None
    for k in range(tries):
        url = BASE + q + f"&_={now_ms()}{k}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bitget-candle-mirror/1.0",
                                                       "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=20) as r:
                j = json.loads(r.read().decode())
            if j.get("code") != "00000":
                raise RuntimeError(f"api code {j.get('code')} {j.get('msg')}")
            rows = []
            for x in j.get("data") or []:
                rows.append([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])])
            return rows
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (k + 1))
    raise RuntimeError(f"{sym} {gran}: {last_err}")


def fetch_series(sym, gran, need):
    """最新一批先抓，新鮮度不過就換 limit（不同快取鍵）；再用 endTime 往回翻頁到夠數。"""
    step, t = STEP[gran], now_ms()
    batch, used = None, None
    for lim in (200, 199, 198, 197, 96):
        rows = get(sym, gran, lim)
        closed = [r for r in rows if r[0] + step <= t]
        if closed and t - max(r[0] for r in closed) - step <= FRESH[gran]:
            batch, used = rows, lim
            break
    if batch is None:
        raise RuntimeError(f"{sym} {gran}: 所有 limit 都回過期資料（CDN）")
    have = {r[0]: r for r in batch}
    pages = 0
    while len(have) < need + 2 and pages < 12:
        oldest = min(have)
        more = get(sym, gran, 200, end_time=oldest)
        new = [r for r in more if r[0] < oldest]
        if not new:
            break  # 上市時間不夠長，到底了
        for r in new:
            have[r[0]] = r
        pages += 1
        time.sleep(0.25)
    rows = sorted(have.values())
    rows = [r for r in rows if r[0] + step <= t]  # 只留已收盤
    return rows[-need:] if len(rows) > need else rows, used, pages


def validate(rows, gran):
    step = STEP[gran]
    gaps = [(a[0], b[0]) for a, b in zip(rows, rows[1:]) if b[0] - a[0] != step]
    chain = [(b[0], a[4], b[1]) for a, b in zip(rows, rows[1:]) if abs(b[1] - a[4]) > 1e-9 * max(1, a[4])]
    align = [r[0] for r in rows if gran in ("1D", "1W") and r[0] % 86_400_000 != 57_600_000]
    return gaps, chain, align


def fmt(v):
    s = repr(v)
    return s[:-2] if s.endswith(".0") else s


def write_csv(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(f"{r[0]},{fmt(r[1])},{fmt(r[2])},{fmt(r[3])},{fmt(r[4])},{fmt(r[5])}\n")
    os.replace(tmp, path)


def main():
    mode, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    spath = os.path.join(out, "status.json")
    try:
        status = json.load(open(spath))
    except Exception:  # noqa: BLE001
        status = {}
    status.setdefault("files", {})
    jobs = ([(s, g, CORE_NEED[g]) for s in CORE for g in ("1D", "4H")] if mode == "core"
            else [(s, "1W", WATCH_NEED["1W"]) for s in WATCH])
    t = now_ms()
    for sym, gran, need in jobs:
        key = f"{sym}_{gran}"
        st = {"checked_at": t}
        try:
            for attempt in range(2):  # 驗證沒過就整串重抓一次
                rows, lim, pages = fetch_series(sym, gran, need)
                gaps, chain, align = validate(rows, gran)
                if not gaps and not align and not (chain and sym in ("BTCUSDT", "ETHUSDT")):
                    break
                time.sleep(3)
            st.update({"rows": len(rows), "first": rows[0][0] if rows else None,
                       "last": rows[-1][0] if rows else None, "limit_used": lim, "pages": pages,
                       "gaps": len(gaps), "chain_breaks": len(chain), "misaligned": len(align)})
            problems = []
            if gaps:
                problems.append(f"{len(gaps)} 個時間缺口，第一個 {gaps[0]}")
            if align:
                problems.append(f"{len(align)} 根日界未對齊 UTC+8")
            if chain and sym in ("BTCUSDT", "ETHUSDT"):
                problems.append(f"{len(chain)} 處 open≠前收，第一處 {chain[0]}")
            elif chain:
                st["chain_note"] = f"{len(chain)} 處 open≠前收（傳統市場永續，僅記錄）"
            if problems:
                st["ok"] = False
                st["error"] = "；".join(problems) + "。未覆寫舊檔。"
            else:
                write_csv(os.path.join(out, f"{key}.csv"), rows)
                st["ok"] = True
                st["written_at"] = t
        except Exception as e:  # noqa: BLE001
            st.update({"ok": False, "error": f"{e}。未覆寫舊檔。"})
        prev = status["files"].get(key, {})
        for k in ("written_at",):
            if k not in st and k in prev:
                st[k] = prev[k]
        status["files"][key] = st
        print(key, "OK" if st.get("ok") else "FAIL", st.get("rows"), st.get("error", ""))
    status["updated_at"] = t
    status["note"] = ("ts = 開盤時間（毫秒，UTC）。只含已收盤 K。欄位 ts,open,high,low,close,volume(base)。"
                      "日線/週線以 UTC+8 00:00 為界。")
    with open(spath, "w") as f:
        json.dump(status, f, ensure_ascii=False, indent=1, sort_keys=True)
    if not any(v.get("ok") for k, v in status["files"].items() if v.get("checked_at") == t):
        sys.exit(1)


if __name__ == "__main__":
    main()
