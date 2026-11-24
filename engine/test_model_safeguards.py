import datetime as dt
from zoneinfo import ZoneInfo
import surprise as S
import predict as P

def main():
    ny=ZoneInfo("America/New_York")
    start=dt.datetime(2020,1,1,8,30,tzinfo=ny)
    pts=[]
    for i in range(100):
        t=start+dt.timedelta(days=i)
        pts.extend([(t,1.,i%2),(t+dt.timedelta(hours=1),1.,(i+1)%2)])
    preds,_=S.walk_forward(pts,"2h")
    assert preds and all(dt.date.fromisoformat(r["training_end"])<=r["when"].date()-dt.timedelta(days=7) for r in preds)
    for a,b in zip(preds,preds[1:]):
        if a["when"].date()==b["when"].date():
            assert a["p"]==b["p"] and a["p0"]==b["p0"]
    assert not S.window_finished("gold2h",start,start+dt.timedelta(minutes=119))
    assert S.window_finished("gold2h",start,start+dt.timedelta(minutes=120))
    assert not S.window_finished("gold",start,start.replace(hour=16))
    assert S.window_finished("gold",start,start.replace(hour=17,minute=15))
    m={"groups":{"inflation":{"gold2h":{"proven":True}}}}
    P.suspend_event_qualification(m)
    assert m["groups"]["inflation"]["gold2h"]["historical_candidate"] and not m["groups"]["inflation"]["gold2h"]["proven"]
    assert "brierSkillBase" in S.evaluate(preds)
    print("event audit safeguards passed")
if __name__=="__main__":
    main()
