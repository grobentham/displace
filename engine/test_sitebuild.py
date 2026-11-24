import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
import sitebuild as S
import publisher as P

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
        assert S.build(site)==1
        content=(site/"reports"/(r["id"]+".html")).read_text()
        assert "&lt;script&gt;" in content and "<script>" not in content
        assert S.BASE+"reports/"+r["id"]+".html" in content
        assert len(ET.parse(site/"sitemap.xml").getroot())==len(S.PAGES)+2
        assert S.build(site)==1
    print("static site build tests passed")
if __name__=="__main__":
    main()
