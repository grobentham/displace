"""Static HTML checks for intelligence routes and shared navigation."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

SITE=Path(__file__).resolve().parent.parent/"site"
PAGES=("macro","signals","relationships","atlas","research","research-v2","research-v3","publications","open","search","research-hub","validation")
class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=[]
        self.links=[]
        self.assets=[]
        self.title=False
        self.canonical=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if a.get("id"): self.ids.append(a["id"])
        if tag=="title": self.title=True
        if tag=="a" and a.get("href"): self.links.append(a["href"])
        if tag=="link" and a.get("rel")=="canonical": self.canonical.append(a.get("href"))
        if tag=="link" and a.get("rel")=="stylesheet": self.assets.append(a.get("href"))
        if tag=="script" and a.get("src"): self.assets.append(a["src"])

def main():
    for name in PAGES:
        path=SITE/(name+".html")
        p=Page()
        p.feed(path.read_text())
        assert p.title and len(p.canonical)==1,name
        assert len(p.ids)==len(set(p.ids)),name
        for a in p.assets:
            u=urlsplit(a)
            if not u.scheme: assert (SITE/u.path).is_file(),(name,a)
        for a in p.links:
            u=urlsplit(a)
            if not u.scheme and not u.path.startswith("/") and u.path.endswith(".html"):
                assert (SITE/u.path).is_file(),(name,a)
        assert "search.html" in p.links and "research-hub.html" in p.links and "index.html#bias" in p.links,name
    print("intelligence route audit passed")
if __name__=="__main__":
    main()
