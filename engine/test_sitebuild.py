import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
import sitebuild as S
import publisher as P
import publication
from gate import forecast_view_errors

def main():
    r={"version":1,"id":"daily-2026-11-24","kind":"daily","title":"Test <script>","generated_at":"2026-11-24T12:00:00+00:00",
       "sources":[{"path":"macro/current.json","asof":"2026-11-24","sha256":"0"*64}],
       "sections":[{"title":"Example","lines":["<script>alert(1)</script>"]}],"limitations":"Test"}
    with tempfile.TemporaryDirectory() as t:
        site=Path(t)
        root=site/"data/publications"
        P.jsonwrite(root/"reports"/(r["id"]+".json"),r)
        cat=P.catalog([r])
        P.jsonwrite(root/"index.json",cat)
        P.write(root/"feed.xml",P.rss(cat))
        nq={"session":{"date":"2026-11-25","open":"2026-11-24T18:00:00-05:00","close":"2026-11-25T17:00:00-05:00","halts":[]},
            "range":{"points":776,"lo":456,"hi":1328},"levels":{"high":26350.75,"low":25905.25},
            "takes":{"high":{"p":0.64},"low":{"p":0.73}},"private_placeholder":"excluded"}
        nq.update(candle="2026-11-24", forecast_at="2026-11-24T22:30:00+00:00", touch=[],
                  tier="base", bias="long", p_up=.54, base_up=.54)
        row = {"market": "nq", "candle": nq["candle"], "for": "2026-11-25", "logged": nq["forecast_at"],
               **publication.forecast_values(nq)}
        nq["forecast_id"] = publication.identity(row)
        bias={"for":"2026-11-25","asof":"2026-11-25T10:00:00+00:00","markets":{"nq":nq}}
        es = {**nq, "range": {"points": 78, "lo": 45, "hi": 132}}
        es_row = {**row, "market": "es", **publication.forecast_values(es)}
        es["forecast_id"] = publication.identity(es_row)
        bias["markets"]["es"] = es
        events=[{"date":"2026-11-25","time":"14:00","impact":"medium","title":"Beige Book"},
                {"date":"2026-11-26","time":"08:30","impact":"high","title":"Other day"},
                {"date":"2026-11-25","time":"invalid","impact":"high","title":"Bad time"}]
        P.jsonwrite(site/"data/bias/current.json",bias)
        P.jsonwrite(site/"data/bias/log.json", {"entries": [row, es_row]})
        P.jsonwrite(site/"data/calendar/events.json",{"events":events})
        P.jsonwrite(site/"data/open/current.json",{"by_market":{"nq":{"n":3}}})
        assert S.build(site)==1
        brief_root=site/"data/briefs/mnq"
        dated=P.load(brief_root/"2026-11-25.json")
        assert dated==P.load(brief_root/"latest.json")
        assert dated["asof"] == nq["forecast_at"] and dated["forecast_id"] == nq["forecast_id"]
        assert forecast_view_errors(site / "data") == []
        P.jsonwrite(brief_root / "latest.json", {**dated, "asof": bias["asof"]})
        assert forecast_view_errors(site / "data") == ["latest.json differs from the published NQ forecast"]
        assert dated["news"]==[{"title":"Beige Book","instant":"2026-11-25T14:00:00-05:00","time_ny":"14:00","impact":"medium"}]
        assert dated["live_count"]==3 and "private_placeholder" not in str(dated)
        content=(site/"reports"/(r["id"]+".html")).read_text()
        assert "&lt;script&gt;" in content and "<script>" not in content
        assert S.BASE+"reports/"+r["id"]+".html" in content
        assert len(ET.parse(site/"sitemap.xml").getroot())==len(S.PAGES)+4
        es = (site / "sessions/es/2026-11-25.html").read_text(encoding="utf-8")
        assert "ES session brief" in es and "45–132 points" in es
        assert "?market=es#session-plan" in es and 'property="og:title"' in es
        nq["session"]["date"]="2026-11-27"
        P.jsonwrite(site/"data/bias/current.json",bias)
        assert S.build(site)==1
        assert P.load(brief_root/"2026-11-25.json")==dated
        assert P.load(brief_root/"latest.json")["date"]=="2026-11-27"
    print("static site build tests passed")
if __name__=="__main__":
    main()
