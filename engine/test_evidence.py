import copy
import datetime as dt
import evidence as E
import publication as P

def main():
    now=dt.datetime(2026,11,24,20,tzinfo=dt.timezone.utc)
    row={"market":"nq","candle":"2026-11-19","for":"2026-11-20","logged":"2026-11-19T21:30:00+00:00",
         "eligible":True,"tier":"base","bias":"long","p_up":.6,"base_up":.5,"p_high":.5,"p_low":.5,
         "range_lo":1,"range_hi":2,"day":"2026-11-20","scored":1,"up":1,"highTaken":1,"lowTaken":0,"inRange":1}
    receipts=P.record([row],{},dt.datetime(2026,11,19,22,tzinfo=dt.timezone.utc),"run1")
    doc=E.make([(row,"bias/log.json")],receipts,[],[],now,[])
    assert doc["forecast_counts"]["verified_resolved"]==1
    m=doc["by_market"]["nq"]
    assert abs(m["brier"]-.16)<1e-9 and abs(m["brier_skill"]-.36)<1e-9
    assert m["tested_direction_n"]==0 and m["tested_direction_accuracy"] is None
    assert not E.check(doc)
    assert E.ledger([(dict(row,day="2026-11-23"),"archive")],receipts,now)[0]["status"]=="verified_invalid_outcome"
    assert E.ledger([(dict(row,void=True),"archive")],receipts,now)[0]["status"]=="void"
    assert E.ledger([(dict(row,eligible=False),"archive")],receipts,now)[0]["status"]=="late"
    assert E.ledger([(row,"archive")],{},now)[0]["status"]=="unverified"
    late=P.record([row],{},E.cutoff(row),"run2")
    assert E.ledger([(row,"archive")],late,now)[0]["status"]=="unverified"
    holiday = dict(row, candle="2026-11-25", logged="2026-11-25T22:02:00+00:00", scored=0,
                   **{"for": "2026-11-27"})
    open_time = dt.datetime(2026, 11, 25, 23, tzinfo=dt.timezone.utc)
    assert E.cutoff(holiday) == open_time
    timely = P.record([holiday], {}, open_time - dt.timedelta(minutes=1), "holiday")
    assert E.ledger([(holiday, "active")], timely, open_time)[0]["status"] == "verified_pending"
    late = P.record([holiday], {}, open_time + dt.timedelta(minutes=1), "holiday")
    assert E.ledger([(holiday, "active")], late, open_time)[0]["status"] == "unverified"
    assert E.ledger([(dict(row,scored=0),"archive")],receipts,now)[0]["status"]=="verified_overdue"
    tampered=copy.deepcopy(doc)
    tampered["by_market"]["nq"]["brier"]=0
    assert E.check(tampered)
    try:
        E.ledger([(row,"active"),(row,"archive")],receipts,now)
        raise AssertionError("duplicate accepted")
    except ValueError:
        pass
    print("evidence tests passed")

if __name__=="__main__":
    main()
