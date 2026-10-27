#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
檢查 data 分支裡的 K 線夠不夠新。

  python3 check_fresh.py DATA_DIR BTCUSDT_4H BTCUSDT_1D ...

每個檔案的「最後一根已收盤 K」必須正好是現在應該有的那一根：
  4H：現在所在 4H 的前一根；1D：UTC+8 昨天；1W：UTC+8 上一個完整週（週一開盤）。
全部通過 exit 0，否則 exit 1。stdout 印 JSON 說明每個檔案的狀況。
"""
import sys, json, time

H4, D1, W1 = 14_400_000, 86_400_000, 604_800_000
OFF = 57_600_000  # UTC+8 午夜 = UTC 16:00


def expected(gran, now):
    if gran == "4H":
        return (now // H4) * H4 - H4
    if gran == "1D":
        return ((now - OFF) // D1) * D1 + OFF - D1
    if gran == "1W":
        # 週線開盤在 UTC+8 週一 00:00 = UTC 週日 16:00；epoch(1970-01-01) 是週四，+3 天是週日
        mon = 3 * D1 + OFF
        return ((now - mon) // W1) * W1 + mon - W1
    raise ValueError(gran)


def main():
    data, keys = sys.argv[1], sys.argv[2:]
    now = int(time.time() * 1000)
    st = json.load(open(f"{data}/status.json"))
    out, ok_all = {}, True
    for k in keys:
        gran = k.rsplit("_", 1)[1]
        f = st.get("files", {}).get(k, {})
        last = None
        try:
            with open(f"{data}/{k}.csv") as fh:
                for line in fh:
                    if line.strip():
                        last = int(line.split(",", 1)[0])
        except FileNotFoundError:
            pass
        exp = expected(gran, now)
        ok = last is not None and last >= exp
        ok_all &= ok
        out[k] = {"ok": ok, "檔案最後一根": last, "應有": exp,
                  "落後根數": None if last is None else max(0, (exp - last) // {"4H": H4, "1D": D1, "1W": W1}[gran]),
                  "鏡像最後檢查": f.get("checked_at"), "鏡像狀態": "正常" if f.get("ok") else f.get("error")}
    print(json.dumps({"now": now, "fresh": ok_all, "files": out}, ensure_ascii=False, indent=1))
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
