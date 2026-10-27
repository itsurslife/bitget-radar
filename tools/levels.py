#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日水位表 — 支撐壓力 / 量能 / 前高前低  v1.0"""
import sys, csv, json

PIVK   = 3
PIVD   = 3
MINDIST= 0.3
MAXDIST= 4.0
TOL    = 0.004
NLEV   = 3
VOLN   = 20

def rd(p):
    out=[]
    for r in csv.reader(open(p)):
        r=[x.strip() for x in r if x.strip()!='']
        if len(r)<6: continue
        try: out.append([int(r[0])]+[float(x) for x in r[1:6]])
        except ValueError: continue
    out.sort(); return out

def atr(R,n=14):
    if len(R)<n+1: return None
    tr=[R[i][2]-R[i][3] if i==0 else max(R[i][2]-R[i][3],abs(R[i][2]-R[i-1][4]),abs(R[i][3]-R[i-1][4])) for i in range(len(R))]
    a=sum(tr[:n])/n
    for i in range(n,len(tr)): a=(a*(n-1)+tr[i])/n
    return a

def fmt(x):
    if x>=1000:  return f"{x:,.0f}"
    if x>=100:   return f"{x:,.1f}"
    if x>=1:     return f"{x:,.3f}"
    return f"{x:.4f}"

def main():
    sym,fD,fH = sys.argv[1:4]
    o={"symbol":sym,"errors":[]}
    D=rd(fD); H=rd(fH)
    if len(D)<21: o["errors"].append(f"日線只有 {len(D)} 根，需要 21")
    if len(H)<60: o["errors"].append(f"4H 只有 {len(H)} 根，需要 60")
    for rows,step,name in [(D,86400000,"日線"),(H,14400000,"4H")]:
        g=[(a[0],b[0]) for a,b in zip(rows,rows[1:]) if b[0]-a[0]!=step]
        if g: o["errors"].append(f"{name} 有 {len(g)} 個時間缺口，第一個在 {g[0]}")
    if o["errors"]:
        o["ladder"]="（資料異常，未產生水位表）"; print(json.dumps(o,ensure_ascii=False,indent=1)); return

    px = H[-1][4]
    a4 = atr(H)

    d=D[-1]
    avgvD = sum(x[5] for x in D[-VOLN-1:-1])/VOLN
    o["前一日"]={"日期ms":d[0],"高":d[2],"低":d[3],"收":d[4],
                 "量":round(d[5],2),"量/20日均量":round(d[5]/avgvD,2) if avgvD else None}

    cur=[x for x in H if x[0]>=d[0]+86400000]
    if cur:
        o["今日至今"]={"開":cur[0][1],"高":max(x[2] for x in cur),"低":min(x[3] for x in cur),
                       "現價":px,"已走 4H 根數":len(cur),"量":round(sum(x[5] for x in cur),2)}
    else:
        o["今日至今"]=None

    w=H[-6:]
    hi24,lo24=max(x[2] for x in w),min(x[3] for x in w)
    avgvH=sum(x[5] for x in H[-VOLN-1:-1])/VOLN
    o["近24小時"]={"高":hi24,"低":lo24,"量":round(sum(x[5] for x in w),2),
                   "現價在區間%":round((px-lo24)/(hi24-lo24)*100) if hi24>lo24 else None}
    o["量能"]={"最新4H量":round(H[-1][5],2),"4H_20根均量":round(avgvH,2),
               "最新4H倍數":round(H[-1][5]/avgvH,2) if avgvH else None,
               "近5根4H倍數":[round(x[5]/avgvH,2) for x in H[-5:]] if avgvH else None}

    raw=[]
    for j in range(PIVK,len(H)-PIVK):
        wd=H[j-PIVK:j+PIVK+1]
        if H[j][2]==max(x[2] for x in wd) and sum(1 for x in wd if x[2]==H[j][2])==1: raw.append((H[j][2],"4H"))
        if H[j][3]==min(x[3] for x in wd) and sum(1 for x in wd if x[3]==H[j][3])==1: raw.append((H[j][3],"4H"))
    for j in range(PIVD,len(D)-PIVD):
        wd=D[j-PIVD:j+PIVD+1]
        if D[j][2]==max(x[2] for x in wd) and sum(1 for x in wd if x[2]==D[j][2])==1: raw.append((D[j][2],"日線"))
        if D[j][3]==min(x[3] for x in wd) and sum(1 for x in wd if x[3]==D[j][3])==1: raw.append((D[j][3],"日線"))
    raw.sort()
    clusters=[]
    for v,tf in raw:
        if clusters and v <= clusters[-1]["sum"]/clusters[-1]["n"]*(1+TOL):
            clusters[-1]["sum"]+=v; clusters[-1]["n"]+=1; clusters[-1]["tf"].add(tf)
        else:
            clusters.append({"sum":v,"n":1,"tf":{tf}})
    C=[{"level":c["sum"]/c["n"],"touches":c["n"],"tf":sorted(c["tf"])} for c in clusters]
    mind = MINDIST*a4 if a4 else 0
    maxd = MAXDIST*a4 if a4 else float("inf")
    def pick(side):
        pool=[c for c in C if (c["level"]>px if side>0 else c["level"]<px)
              and mind <= abs(c["level"]-px) <= maxd]
        pool.sort(key=lambda c: abs(c["level"]-px))
        strong=[c for c in pool if c["touches"]>=2]
        weak=[c for c in pool if c["touches"]<2]
        out=(strong+weak)[:NLEV]
        out.sort(key=lambda c: c["level"], reverse=(side<0))
        return out
    res=pick(1); sup=pick(-1)
    seriesHi=max(x[2] for x in H); seriesLo=min(x[3] for x in H)
    if seriesHi>px and abs(seriesHi-px)<=maxd and all(abs(seriesHi-r["level"])/seriesHi>TOL for r in res):
        res.append({"level":seriesHi,"touches":1,"tf":["4H"],"label":"區間高"}); res=res[:NLEV+1]
        res.sort(key=lambda c:c["level"])
    if seriesLo<px and abs(seriesLo-px)<=maxd and all(abs(seriesLo-s["level"])/seriesLo>TOL for s in sup):
        sup.append({"level":seriesLo,"touches":1,"tf":["4H"],"label":"區間低"}); sup=sup[:NLEV+1]
        sup.sort(key=lambda c:-c["level"])
    def strength(n): return "強" if n>=3 else ("中" if n==2 else "弱")
    def deco(c):
        return {"價位":round(c["level"],4),"測試次數":c["touches"],"強度":strength(c["touches"]),
                "來源":"+".join(c["tf"]),
                "距現價%":round((c["level"]-px)/px*100,2),
                "距現價_ATR倍":round(abs(c["level"]-px)/a4,2) if a4 else None,
                **({"標記":c["label"]} if "label" in c else {})}
    o["壓力"]=[deco(c) for c in res]
    o["支撐"]=[deco(c) for c in sup]
    o["濾除規則"]=(f"只列距現價 {MINDIST}~{MAXDIST} 倍 4H ATR（約 {round(mind,2)} ~ {round(maxd,2)}）之間的水位。"
                   f"太近的落在雜訊帶，太遠的今天走不到。")
    o["真空區"]={"上方": len([c for c in C if c["level"]>px and mind<=abs(c["level"]-px)<=maxd])==0,
                 "下方": len([c for c in C if c["level"]<px and mind<=abs(c["level"]-px)<=maxd])==0}
    o["4H_ATR"]=round(a4,4) if a4 else None
    o["樣本"]={"4H根數":len(H),"日線根數":len(D),"叢集容差%":TOL*100,"擺動點左右根數":PIVK}

    L=[]
    for c in o["壓力"][::-1]:
        L.append(f"  壓力 {fmt(c['價位']):>10}  {'█'*min(c['測試次數'],4):<4} ×{c['測試次數']} {c['強度']}  {c['距現價%']:+.2f}%{'  '+c['標記'] if '標記' in c else ''}")
    L.append(f"  ─────{'─'*11} {fmt(px):>10}  ◀ 現價    24h 區間 {o['近24小時']['現價在區間%']}%")
    for c in o["支撐"]:
        L.append(f"  支撐 {fmt(c['價位']):>10}  {'█'*min(c['測試次數'],4):<4} ×{c['測試次數']} {c['強度']}  {c['距現價%']:+.2f}%{'  '+c['標記'] if '標記' in c else ''}")
    if len(o["壓力"])<NLEV: L.insert(0,f"  （上方 {MAXDIST} 倍 ATR 內只有 {len(o['壓力'])} 個水位）")
    if len(o["支撐"])<NLEV: L.append(f"  （下方 {MAXDIST} 倍 ATR 內只有 {len(o['支撐'])} 個水位 —— 再往下是真空）")
    o["ladder"]="\n".join(L)
    print(json.dumps(o,ensure_ascii=False,indent=1))

main()
