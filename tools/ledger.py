#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
紀錄簿工具  v1.0 — 新增判定、結算，兩件事都只動該動的欄位。

  python3 ledger.py append  LEDGER.json NEW_ROWS.json DATA_DIR  > OUT.json
  python3 ledger.py settle  LEDGER.json DATA_DIR                > OUT.json

DATA_DIR 是 data 分支（含 <SYM>_4H.csv）。報告寫到 stderr，新的 JSON 陣列寫到 stdout。

append：
  - 只在尾端追加，筆數必為 N+len(NEW)，否則失敗（exit 2）。
  - 重複單判定（修 2026-09 以後 dup 永遠為空的錯誤）：新的下單列若與更早一張「非重複」下單
    同標的、同方向、同限價，且那張在新決策點當下仍「活著」（48h 掛單窗內未成交，或已成交且
    72h 持有窗內未觸停損/目標），就把新列的 dup 設成那張的 t，並把那張的 rep 加 1。
    原單已經結束（停損、觸目標、撤單、時間出場）的話，新列是一筆新交易，dup 維持 null。
    「活著」用 data 分支的 4H 實際行情判斷，不用猜。

settle：規則與既有結算排程完全相同（48h 掛單 + 72h 持有、同根兩者都觸算停損、
  滿 120h 才結算、R 四捨五入到 2 位），只改 out 與 R，筆數必須不變。
"""
import sys, json, csv, datetime as dt

SYM = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "CL": "CLUSDT", "NATGAS": "NATGASUSDT", "MU": "MUUSDT"}
STEP = 14_400_000
FILL_BARS, HOLD_BARS, SETTLE_H = 12, 18, 120


def t_ms(s):
    return int((dt.datetime.strptime(s, "%Y-%m-%d %H:%M") - dt.timedelta(hours=8))
               .replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def load_4h(data, sym):
    rows = []
    for r in csv.reader(open(f"{data}/{SYM[sym]}_4H.csv")):
        rows.append([int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4])])
    rows.sort()
    return rows


def is_order(r):
    return isinstance(r.get("v"), str) and r["v"].startswith("下單") and None not in (r.get("e"), r.get("s"), r.get("g"))


def side(r):
    return 1 if "做多" in r["v"] else -1


def simulate(r, bars, until=None):
    """回傳 (狀態, out, R)。狀態：'live' 仍在掛單或持倉；'done' 已結束；'nodata' 資料不夠。
    bars 為 4H 升冪；只用收盤時間 <= until 的 K（until=None 代表用全部）。"""
    t0 = t_ms(r["t"])
    after = [b for b in bars if b[0] >= t0 and (until is None or b[0] + STEP <= until)]
    d, e, s, g = side(r), r["e"], r["s"], r["g"]
    fill = None
    for k, b in enumerate(after[:FILL_BARS]):
        if (d > 0 and b[3] <= e) or (d < 0 and b[2] >= e):
            fill = k
            break
    if fill is None:
        if len(after) >= FILL_BARS:
            return "done", "未成交", 0.0
        return "pending", None, None
    hold = after[fill:fill + HOLD_BARS]
    for b in hold:
        hit_t = (b[2] >= g) if d > 0 else (b[3] <= g)
        hit_s = (b[3] <= s) if d > 0 else (b[2] >= s)
        if hit_s:
            return "done", "停損", -1.0
        if hit_t:
            return "done", "觸及目標", round(float(r["rr"]), 2)
    if len(hold) >= HOLD_BARS:
        c = hold[-1][4]
        risk, cost = abs(e - s), e * 0.0016
        return "done", "時間出場", round((d * (c - e) - cost) / (risk + cost), 2)
    return "holding", None, None


def append(ledger, new, data):
    n0 = len(ledger)
    out = [dict(x) for x in ledger]
    cache = {}
    for row in new:
        row = dict(row)
        row.setdefault("dup", None)
        row.setdefault("rep", None)
        if is_order(row) and row.get("sym") in SYM:
            bars = cache.setdefault(row["sym"], load_4h(data, row["sym"]))
            tn = t_ms(row["t"])
            for prev in reversed(out):
                if (prev.get("sym") == row["sym"] and is_order(prev) and not prev.get("dup")
                        and side(prev) == side(row) and abs(prev["e"] - row["e"]) <= 1e-9 * abs(row["e"])
                        and t_ms(prev["t"]) < tn):
                    st, _, _ = simulate(prev, bars, until=tn)
                    if st == "holding":   # 原單已成交、還在持倉 → 新列只是管理，不是新單
                        row["dup"] = prev["t"]
                        prev["rep"] = (prev.get("rep") or 1) + 1
                        print(f"  {row['t']} {row['sym']} 原單 {prev['t']} 持倉中 → 新列標 dup", file=sys.stderr)
                    elif st == "pending":  # 原單還沒成交 → 改掛：新列接手，原列退場
                        prev["dup"] = row["t"]
                        row["rep"] = (prev.get("rep") or 1) + 1
                        print(f"  {row['t']} {row['sym']} 原單 {prev['t']} 未成交 → 由新列接手，原列標 dup", file=sys.stderr)
                    break
        out.append(row)
    if len(out) != n0 + len(new):
        print(f"筆數異常：{n0}+{len(new)} != {len(out)}", file=sys.stderr)
        sys.exit(2)
    return out


def settle(ledger, data):
    now = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    out = [dict(x) for x in ledger]
    cache, done = {}, []
    for r in out:
        if not (is_order(r) and not r.get("dup") and r.get("out") in ("—", None)):
            continue
        if r.get("sym") not in SYM or now - t_ms(r["t"]) < SETTLE_H * 3_600_000:
            continue
        bars = cache.setdefault(r["sym"], load_4h(data, r["sym"]))
        if not bars or bars[0][0] > t_ms(r["t"]):
            print(f"  {r['t']} {r['sym']} 資料不涵蓋決策點，跳過", file=sys.stderr)
            continue
        st, o, R = simulate(r, bars)
        if st != "done":
            print(f"  {r['t']} {r['sym']} 4H 資料尚不足以結算，跳過", file=sys.stderr)
            continue
        r["out"], r["R"] = o, R
        done.append((r["t"], r["sym"], o, R))
    if len(out) != len(ledger):
        print("筆數改變，已中止", file=sys.stderr)
        sys.exit(2)
    for d in done:
        print("  結算", *d, file=sys.stderr)
    print(f"結算 {len(done)} 筆", file=sys.stderr)
    return out


def main():
    cmd = sys.argv[1]
    ledger = json.load(open(sys.argv[2]))
    if cmd == "append":
        res = append(ledger, json.load(open(sys.argv[3])), sys.argv[4])
    elif cmd == "settle":
        res = settle(ledger, sys.argv[3])
    else:
        sys.exit("用法：append LEDGER NEW DATA | settle LEDGER DATA")
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
