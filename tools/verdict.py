#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三層判定 + 下單參數  v1.0"""
import sys, csv, json

COST_PCT   = 0.16
RISK_OK    = 1.0
RISK_HEAD  = 0.5
MIN_NET_RR = 1.5
ROOM = {"A": {"day":0.96, "night":1.41}, "B": {"day":3.20, "night":2.97}}
PIV  = 5
RECENT = 30
RETRACE = 0.618
STOPFIB = 0.786
STOPBUF = 0.2

def rd(p, n):
    out=[]
    for r in csv.reader(open(p)):
        r=[x.strip() for x in r if x.strip()!='']
        if len(r)<n: continue
        try: out.append([int(r[0])]+[float(x) for x in r[1:n]])
        except ValueError: continue
    out.sort(); return out

def check(rows, step, name, need):
    if len(rows) < need: return f"{name} 只有 {len(rows)} 根，需要 {need}"
    g=[(a[0],b[0]) for a,b in zip(rows,rows[1:]) if b[0]-a[0]!=step]
    if g: return f"{name} 有 {len(g)} 個時間缺口，第一個在 {g[0]}"
    return None

def ema(v,n):
    k=2/(n+1); o=[None]*len(v); e=None
    for i in range(len(v)):
        if i<n-1: continue
        e=sum(v[:n])/n if e is None else v[i]*k+e*(1-k); o[i]=e
    return o
def sma(v,n): return [None if i<n-1 else sum(v[i-n+1:i+1])/n for i in range(len(v))]
def atr(R,n=14):
    tr=[R[i][2]-R[i][3] if i==0 else max(R[i][2]-R[i][3],abs(R[i][2]-R[i-1][4]),abs(R[i][3]-R[i-1][4])) for i in range(len(R))]
    o=[None]*len(tr); a=None
    for i in range(len(tr)):
        if i<n-1: continue
        a=sum(tr[:n])/n if a is None else (a*(n-1)+tr[i])/n; o[i]=a
    return o
def pivots(R,k=PIV):
    ph=[];pl=[]
    for j in range(k,len(R)-k):
        w=R[j-k:j+k+1]
        if R[j][2]==max(x[2] for x in w) and sum(1 for x in w if x[2]==R[j][2])==1: ph.append((R[j][0],R[j][2]))
        if R[j][3]==min(x[3] for x in w) and sum(1 for x in w if x[3]==R[j][3])==1: pl.append((R[j][0],R[j][3]))
    return ph,pl

def main():
    sym, fC, fD, fH, sess = sys.argv[1:6]
    eq = float(sys.argv[6]) if len(sys.argv)>6 else 10000.0
    o={"symbol":sym,"session":sess,"errors":[]}

    DC=rd(fC,2); DO=rd(fD,6); H4=rd(fH,5)
    for e in [check(DC,86400000,"日線收盤序列",260),
              check(H4,14400000,"4H 序列",100)]:
        if e: o["errors"].append(e)
    if len(DO)<2: o["errors"].append("日線 OHLC 不足 2 根")
    if o["errors"]:
        o["verdict"]="資料異常，不判定"; print(json.dumps(o,ensure_ascii=False,indent=1)); return

    C=[x[1] for x in DC]; i=len(C)-1
    m20=sma(C,20)
    sd=[None if j<19 else (sum((C[k]-m20[j])**2 for k in range(j-19,j+1))/20)**.5 for j in range(len(C))]
    U=[None if m20[j] is None else m20[j]+2*sd[j] for j in range(len(C))]
    L=[None if m20[j] is None else m20[j]-2*sd[j] for j in range(len(C))]
    e50,e200=ema(C,50),ema(C,200)

    s_mid = 1 if C[i]>m20[i] else -1
    up = sum([U[i]>U[i-1], m20[i]>m20[i-1], L[i]>L[i-1]]); dn = 3-up
    s_bb  = 1 if up>=2 else (-1 if dn>=2 else 0)
    w20=C[i-19:i+1]
    s_20  = 1 if C[i]==max(w20) else (-1 if C[i]==min(w20) else 0)
    ph4,pl4=pivots(H4)
    s_4h=0
    if len(ph4)>=2 and len(pl4)>=2:
        if ph4[-1][1]>ph4[-2][1] and pl4[-1][1]>pl4[-2][1]: s_4h=1
        elif ph4[-1][1]<ph4[-2][1] and pl4[-1][1]<pl4[-2][1]: s_4h=-1
    tot=s_mid+s_bb+s_20+s_4h
    direction = "long" if tot>=3 else ("short" if tot<=-3 else "none")
    o["direction_layer"]={"中軌":s_mid,"布林":s_bb,"20日位置":s_20,"4H結構":s_4h,
                          "合計":tot,"結果":{"long":"偏多","short":"偏空","none":"不做"}[direction]}

    tail = "順風" if (e50[i]>e200[i] and e200[i]>e200[i-10]) else "逆風"
    risk_pct = RISK_OK if tail=="順風" else RISK_HEAD
    o["environment"]={"EMA50":round(e50[i],2),"EMA200":round(e200[i],2),
                      "EMA200斜率10根%":round((e200[i]/e200[i-10]-1)*100,2),
                      "結果":tail,"單筆風險%":risk_pct}

    lo_,hi_ = DO[-1][3], DO[-1][2]; op_,cl_ = DO[-1][1], DO[-1][4]
    rng = hi_-lo_
    uw = (hi_-max(op_,cl_))/rng if rng>0 else 0
    lw = (min(op_,cl_)-lo_)/rng if rng>0 else 0
    pos = (cl_-lo_)/rng if rng>0 else .5
    veto_long  = uw>=0.50 and pos<=0.35
    veto_short = lw>=0.50 and pos>=0.65
    o["reversal_warning"]={"上影%":round(uw*100),"下影%":round(lw*100),"收在區間%":round(pos*100),
                           "量比前日":round(DO[-1][5]/DO[-2][5],2) if DO[-2][5] else None,
                           "禁止做多":veto_long,"禁止做空":veto_short,
                           "解除價(收盤站上)":hi_,"升級價(收盤跌破)":lo_}

    if direction=="none":
        o["verdict"]="空手 — 方向層未達門檻"; print(json.dumps(o,ensure_ascii=False,indent=1)); return
    if direction=="long" and veto_long:
        o["verdict"]="空手 — 反轉警示禁止做多"; print(json.dumps(o,ensure_ascii=False,indent=1)); return
    if direction=="short" and veto_short:
        o["verdict"]="空手 — 反轉警示禁止做空"; print(json.dumps(o,ensure_ascii=False,indent=1)); return

    A=atr(H4); a4=A[-1]; entry=H4[-1][4]; cost=entry*COST_PCT/100
    cutoff = H4[-RECENT][0] if len(H4)>RECENT else H4[0][0]
    leg=None
    if direction=="long":
        cands=[(t,v) for t,v in pl4 if t>=cutoff and v<entry]
        if cands:
            t0,legLo=cands[-1]
            legHi=max(x[2] for x in H4 if x[0]>=t0)
            leg=(legLo,legHi)
    else:
        cands=[(t,v) for t,v in ph4 if t>=cutoff and v>entry]
        if cands:
            t0,legHi=cands[-1]
            legLo=min(x[3] for x in H4 if x[0]>=t0)
            leg=(legLo,legHi)
    if leg is None:
        o["verdict"]=f"空手 — 近 {RECENT} 根 4H 內沒有已確認的結構錨點"
        o["note"]="強勢單邊之後常出現：擺動點需右側 5 根確認，行情還沒給。沒有錨點就沒有可執行的計畫。"
        print(json.dumps(o,ensure_ascii=False,indent=1)); return
    legLo,legHi=leg; span=legHi-legLo
    if span<=0:
        o["verdict"]="空手 — 推進段幅度為零"; print(json.dumps(o,ensure_ascii=False,indent=1)); return
    if direction=="long":
        limit = legHi - span*RETRACE
        stop  = legHi - span*STOPFIB - STOPBUF*a4
        target= legHi
        already = H4[-1][4] <= limit
    else:
        limit = legLo + span*RETRACE
        stop  = legLo + span*STOPFIB + STOPBUF*a4
        target= legLo
        already = H4[-1][4] >= limit
    entry = limit
    o["leg"]={"推進段低":round(legLo,2),"推進段高":round(legHi,2),"幅度":round(span,2),
              "幅度/ATR":round(span/a4,2),"回撤位":RETRACE,"是否已回踩到位":already}

    risk=abs(entry-stop); mult=risk/a4
    style = "A·時段" if mult<=0.6 else ("B·波段" if mult<=1.5 else None)
    reward=abs(target-entry)
    net=(reward-cost)/(risk+cost)
    need_pct=(1.5*(risk+cost)+cost)/entry*100
    room=ROOM["A" if (style or "").startswith("A") else "B"][sess]
    gates={"型態":style is not None,"淨RR>=1.5":net>=MIN_NET_RR,"空間閘門":need_pct<=room}
    o["order"]={"型態":style,"進場":round(entry,2),"停損":round(stop,2),"目標":round(target,2),
                "風險點數":round(risk,2),"風險/ATR":round(mult,2),"4H_ATR":round(a4,2),
                "掛單方式":"限價","成本點數":round(cost,2),"帳面RR":round(reward/risk,2),"淨RR":round(net,2),
                "淨1.5需漲%":round(need_pct,2),"視窗上限%":room,
                "部位":round(eq*risk_pct/100/risk,6),"單筆風險金額":round(eq*risk_pct/100,2)}
    o["gates"]=gates
    if all(gates.values()):
        o["verdict"]=f"下單 {'做多' if direction=='long' else '做空'}（{style}）"
    else:
        fail=[k for k,v in gates.items() if not v]
        o["verdict"]="空手 — 閘門未過：" + "、".join(fail)
    print(json.dumps(o,ensure_ascii=False,indent=1))

main()
