#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三層判定 + 下單參數 — 傳統市場追蹤型永續版  v1.0"""
import sys, csv, json, datetime as dt

COST_PCT   = 0.16
RISK_OK    = 1.0
RISK_HEAD  = 0.5
MIN_NET_RR = 1.5
PIV, RECENT = 5, 30
RETRACE, STOPFIB, STOPBUF = 0.618, 0.786, 0.2
LONGMA = 144
MIN_DAILY = 154

ROOM = {
  "CLUSDT":     {"A":{"day":1.49,"night":1.44}, "B":{"day":5.37,"night":4.31}},
  "NATGASUSDT": {"A":{"day":1.07,"night":1.23}, "B":{"day":3.42,"night":4.03}},
  "MUUSDT":     {"A":{"day":2.01,"night":1.33}, "B":{"day":9.13,"night":8.41}},
}
NOTE = {
  "CLUSDT":     "追蹤 WTI 原油。EIA 庫存每週三、OPEC 會議為排程事件，純技術框架看不到。",
  "NATGASUSDT": "追蹤天然氣。EIA 天然氣庫存每週四；天氣預報是主要驅動，季節性極強。",
  "MUUSDT":     "追蹤 Micron 個股。財報日為排程事件；另有盤前盤後跳空，且無法驗證此永續與現貨的追蹤誤差。",
}

def rd(p, n):
    out=[]
    for r in csv.reader(open(p)):
        r=[x.strip() for x in r if x.strip()!='']
        if len(r)<n: continue
        try: out.append([int(r[0])]+[float(x) for x in r[1:n]])
        except ValueError: continue
    out.sort(); return out

def wk(ts):  return dt.datetime.utcfromtimestamp(ts/1000+8*3600).weekday()
def dstr(ts):return dt.datetime.utcfromtimestamp(ts/1000+8*3600).strftime('%Y-%m-%d')

def ema(v,n):
    k=2/(n+1); o=[None]*len(v); e=None
    for i in range(len(v)):
        if i<n-1: continue
        e=sum(v[:n])/n if e is None else v[i]*k+e*(1-k); o[i]=e
    return o
def sma(v,n): return [None if i<n-1 else sum(v[i-n+1:i+1])/n for i in range(len(v))]
def atr_rows(R,n=14):
    if len(R)<n+1: return None
    tr=[R[i][2]-R[i][3] if i==0 else max(R[i][2]-R[i][3],abs(R[i][2]-R[i-1][4]),abs(R[i][3]-R[i-1][4])) for i in range(len(R))]
    a=sum(tr[:n])/n
    for i in range(n,len(tr)): a=(a*(n-1)+tr[i])/n
    return a
def pivots(R,k=PIV):
    ph=[];pl=[]
    for j in range(k,len(R)-k):
        w=R[j-k:j+k+1]
        if R[j][2]==max(x[2] for x in w) and sum(1 for x in w if x[2]==R[j][2])==1: ph.append((R[j][0],R[j][2]))
        if R[j][3]==min(x[3] for x in w) and sum(1 for x in w if x[3]==R[j][3])==1: pl.append((R[j][0],R[j][3]))
    return ph,pl

def main():
    sym,fD,fH,sess = sys.argv[1:5]
    eq = float(sys.argv[5]) if len(sys.argv)>5 else 10000.0
    o={"symbol":sym,"session":sess,"script":"tradfi v1.0","errors":[],"warnings":[]}
    if sym not in ROOM:
        o["errors"].append(f"{sym} 沒有校準過的空間閘門。這支腳本只認 {list(ROOM)}；未校準的標的不准用別人的門檻。")
        o["verdict"]="不判定 — 標的未校準"; print(json.dumps(o,ensure_ascii=False,indent=1)); return
    o["instrument_note"]=NOTE[sym]

    D=rd(fD,6); H=rd(fH,5)
    for rows,step,name,need in [(D,86400000,"日線",MIN_DAILY),(H,14400000,"4H",100)]:
        if len(rows)<need: o["errors"].append(f"{name} 只有 {len(rows)} 根，需要 {need}")
        g=[(a[0],b[0]) for a,b in zip(rows,rows[1:]) if b[0]-a[0]!=step]
        if g: o["errors"].append(f"{name} 有 {len(g)} 個時間缺口，第一個在 {g[0]}")
    if o["errors"]:
        o["verdict"]="資料異常，不判定"; print(json.dumps(o,ensure_ascii=False,indent=1)); return

    C=[x[4] for x in D]; i=len(C)-1
    o["last_daily"]=dstr(D[i][0]); o["last_4h"]=dstr(H[-1][0]); o["close"]=C[i]

    dow=wk(H[-1][0])
    if dow>=5:
        o["warnings"].append("決策點落在週末，標的休市 → 不下單")
    weekend_ahead = wk(H[-1][0])==4

    m20=sma(C,20)
    sd=[None if j<19 else (sum((C[k]-m20[j])**2 for k in range(j-19,j+1))/20)**.5 for j in range(len(C))]
    U=[m20[j]+2*sd[j] if m20[j] else None for j in range(len(C))]
    L=[m20[j]-2*sd[j] if m20[j] else None for j in range(len(C))]
    s_mid = 1 if C[i]>m20[i] else -1
    up=sum([U[i]>U[i-1],m20[i]>m20[i-1],L[i]>L[i-1]]); dn=3-up
    s_bb = 1 if up>=2 else (-1 if dn>=2 else 0)
    w20=C[i-19:i+1]
    s_20 = 1 if C[i]==max(w20) else (-1 if C[i]==min(w20) else 0)
    ph4,pl4=pivots(H); s_4h=0
    if len(ph4)>=2 and len(pl4)>=2:
        if ph4[-1][1]>ph4[-2][1] and pl4[-1][1]>pl4[-2][1]: s_4h=1
        elif ph4[-1][1]<ph4[-2][1] and pl4[-1][1]<pl4[-2][1]: s_4h=-1
    tot=s_mid+s_bb+s_20+s_4h
    direction = "long" if tot>=3 else ("short" if tot<=-3 else "none")
    o["direction_layer"]={"中軌":s_mid,"布林":s_bb,"20日位置":s_20,"4H結構":s_4h,"合計":tot,
                          "結果":{"long":"偏多","short":"偏空","none":"不做"}[direction]}

    e55,e144=ema(C,55),ema(C,LONGMA)
    valid=sum(1 for x in e144 if x is not None)
    if e144[i] is None or e144[i-10] is None:
        risk_pct=RISK_HEAD
        o["environment"]={"結果":"無法判定","原因":f"EMA{LONGMA} 只有 {valid} 根有效，算不出 10 根斜率",
                          "採用單筆風險%":risk_pct,"說明":"環境層失效時一律按逆風處理（保守）"}
    else:
        tail="順風" if (e55[i]>e144[i] and e144[i]>e144[i-10]) else "逆風"
        risk_pct=RISK_OK if tail=="順風" else RISK_HEAD
        o["environment"]={"EMA55":round(e55[i],4),f"EMA{LONGMA}":round(e144[i],4),
                          f"EMA{LONGMA}斜率10根%":round((e144[i]/e144[i-10]-1)*100,2),
                          "結果":tail,"單筆風險%":risk_pct,
                          "註":f"用 EMA{LONGMA} 代替 EMA200——上市時間不足，EMA200 不存在"}

    op_,hi_,lo_,cl_=D[i][1],D[i][2],D[i][3],D[i][4]; rng=hi_-lo_
    uw=(hi_-max(op_,cl_))/rng if rng>0 else 0
    lw=(min(op_,cl_)-lo_)/rng if rng>0 else 0
    pos=(cl_-lo_)/rng if rng>0 else .5
    veto_long  = uw>=0.50 and pos<=0.35
    veto_short = lw>=0.50 and pos>=0.65
    o["reversal_warning"]={"上影%":round(uw*100),"下影%":round(lw*100),"收在區間%":round(pos*100),
                           "量比前日":round(D[i][5]/D[i-1][5],2) if D[i-1][5] else None,
                           "禁止做多":veto_long,"禁止做空":veto_short,
                           "解除價(收盤站上)":hi_,"升級價(收盤跌破)":lo_}

    Dwd=[x for x in D if wk(x[0])<5]
    a_wd=atr_rows(Dwd); a_all=atr_rows(D)
    Hwd=[x for x in H if wk(x[0])<5]
    a4=atr_rows(Hwd)
    o["atr"]={"日線_只用平日":round(a_wd,4),"日線_含週末":round(a_all,4),
              "週末稀釋%":round((1-a_all/a_wd)*100),
              "4H_只用平日":round(a4,4),"4H_只用平日_佔價格%":round(a4/C[i]*100,2),
              "說明":"停損一律用『只用平日』的 ATR，含週末的值會讓停損過窄"}

    if dow>=5:
        o["verdict"]="空手 — 週末，標的休市"; print(json.dumps(o,ensure_ascii=False,indent=1)); return
    if direction=="none":
        o["verdict"]="空手 — 方向層未達門檻"; print(json.dumps(o,ensure_ascii=False,indent=1)); return
    if direction=="long" and veto_long:
        o["verdict"]="空手 — 反轉警示禁止做多"; print(json.dumps(o,ensure_ascii=False,indent=1)); return
    if direction=="short" and veto_short:
        o["verdict"]="空手 — 反轉警示禁止做空"; print(json.dumps(o,ensure_ascii=False,indent=1)); return

    entry0=H[-1][4]; cost=entry0*COST_PCT/100
    cutoff=H[-RECENT][0] if len(H)>RECENT else H[0][0]
    leg=None
    if direction=="long":
        c=[(t,v) for t,v in pl4 if t>=cutoff and v<entry0]
        if c: t0,lo2=c[-1]; leg=(lo2,max(x[2] for x in H if x[0]>=t0))
    else:
        c=[(t,v) for t,v in ph4 if t>=cutoff and v>entry0]
        if c: t0,hi2=c[-1]; leg=(min(x[3] for x in H if x[0]>=t0),hi2)
    if leg is None:
        o["verdict"]=f"空手 — 近 {RECENT} 根 4H 內沒有已確認的結構錨點"
        print(json.dumps(o,ensure_ascii=False,indent=1)); return
    legLo,legHi=leg; span=legHi-legLo
    if span<=0:
        o["verdict"]="空手 — 推進段幅度為零"; print(json.dumps(o,ensure_ascii=False,indent=1)); return
    if direction=="long":
        entry=legHi-span*RETRACE; stop=legHi-span*STOPFIB-STOPBUF*a4; target=legHi
        already=H[-1][4]<=entry
    else:
        entry=legLo+span*RETRACE; stop=legLo+span*STOPFIB+STOPBUF*a4; target=legLo
        already=H[-1][4]>=entry
    o["leg"]={"推進段低":round(legLo,4),"推進段高":round(legHi,4),
              "幅度/平日4H_ATR":round(span/a4,2),"回撤位":RETRACE,"是否已回踩到位":already}

    risk=abs(entry-stop); mult=risk/a4
    style="A·時段" if mult<=0.6 else ("B·波段" if mult<=1.5 else None)
    reward=abs(target-entry)
    net=(reward-cost)/(risk+cost)
    need=(1.5*(risk+cost)+cost)/entry*100
    room=ROOM[sym]["A" if (style or "").startswith("A") else "B"][sess]
    gates={"型態":style is not None,"淨RR>=1.5":net>=MIN_NET_RR,"空間閘門":need<=room}
    if weekend_ahead and style and style.startswith("B"):
        o["warnings"].append("今天是週五，B 型要持 48-72 小時 → 會裸跨週末，標的休市期間無法停損，週一可能跳空")
    o["order"]={"型態":style,"掛單方式":"限價","進場":round(entry,4),"停損":round(stop,4),"目標":round(target,4),
                "風險":round(risk,4),"風險/平日4H_ATR":round(mult,2),"成本":round(cost,4),
                "帳面RR":round(reward/risk,2),"淨RR":round(net,2),
                "淨1.5需走%":round(need,2),"該標的視窗上限%":room,
                "部位":round(eq*risk_pct/100/risk,6),"單筆風險金額":round(eq*risk_pct/100,2)}
    o["gates"]=gates
    if all(gates.values()):
        o["verdict"]=f"下單 {'做多' if direction=='long' else '做空'}（{style}）"
    else:
        o["verdict"]="空手 — 閘門未過：" + "、".join(k for k,v in gates.items() if not v)
    print(json.dumps(o,ensure_ascii=False,indent=1))

main()
