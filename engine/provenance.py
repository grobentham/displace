"""Git-backed dataset provenance. No additional raw market-data copies."""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
ARCHIVE="research/provenance/runs"
PUBLIC="site/data/provenance/current.json"
OUTPUTS=("bias/current.json","bias/log.json","direction/current.json","direction/log.json",
         "research/discovery.json","research/discovery-v2.json","macro/current.json","signals/current.json",
         "relationships/current.json","atlas/current.json","validation/current.json","validation/models.json",
         "open/current.json","calendar/events.json","publications/index.json")
POLICY=("Captured files are saved current-vintage inputs and outputs, not proof of historical availability. "
        "Git commit history retains the bytes; manifests contain hashes, not additional raw data copies. "
        "A new-to-cache observation is not necessarily a first release. Capture is not a Pages deployment receipt.")

def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def git(root,*args,check=True):
    return subprocess.run(["git",*args],cwd=root,check=check,capture_output=True).stdout

def capture_id():
    run=os.environ.get("GITHUB_RUN_ID","")
    attempt=os.environ.get("GITHUB_RUN_ATTEMPT","")
    if not run.isdigit() or not attempt.isdigit():
        return None
    return run+"-"+attempt

def fingerprint(obj):
    """For JSON-compatible normalized model inputs, not a raw-file hash."""
    return digest(obj)

def read_json(path):
    return json.loads(path.read_text())

def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False)+"\n")
    os.replace(tmp,path)

def record(path,data):
    return {"path":path,"sha256":hash_bytes(data),"bytes":len(data)}

def selected(root):
    # Enumerate tracked and nonignored files, not temporary or secret local files.
    names=git(root,"ls-files","-z","--cached","--others","--exclude-standard","--","engine/cache","engine","research").decode().split("\0")
    paths={p for p in names if p and ((p.startswith("engine/cache/") and p.endswith(".json"))
              or (p.startswith("engine/") and p.count("/")==1 and p.endswith((".py",".json")))
              or (p.startswith("research/") and p.count("/")==1 and p.endswith(".json")))}
    paths.update("site/data/"+p for p in OUTPUTS)
    paths.add(".github/workflows/engine.yml")
    return sorted(paths)

def observations(path,data):
    doc=json.loads(data)
    if not isinstance(doc,dict):
        return None
    rows=doc.get("rows",[])
    if path.startswith(("engine/cache/macro/","engine/cache/series/")):
        return {r[0]:r[1] for r in rows}
    if path.startswith("engine/cache/tv/"):
        return {r["t"]+"|"+r["d"]:{k:r.get(k) for k in ("a","f","p")} for r in rows}
    return None

def changes(path,before,after):
    new=observations(path,after)
    if new is None:
        return None
    if before is None:
        return {"baseline_observations":len(new),"new_to_cache":None,"revised":None,"removed":None,"changes":[]}
    old=observations(path,before)
    if old is None:
        raise ValueError("Observation format changed: "+path)
    entries=[]
    for key in sorted(set(old)|set(new)):
        if key not in old:
            kind="new_to_cache"
        elif key not in new:
            kind="removed"
        elif old[key]!=new[key]:
            kind="revised"
        else:
            continue
        entries.append({"observation":key,"kind":kind,"before_sha256":digest(old[key]) if key in old else None,
                        "after_sha256":digest(new[key]) if key in new else None})
    return {"baseline_observations":None,**{k:sum(e["kind"]==k for e in entries) for k in ("new_to_cache","revised","removed")},"changes":entries}

def previous(root):
    paths=sorted((root/ARCHIVE).glob("*.json"))
    if not paths:
        return None
    # Capture order, not lexicographic run ID order.
    docs=[read_json(p) for p in paths]
    return max(docs,key=lambda d:(d["captured_at"],d["id"]))

def build(root,ident,now):
    if not re.fullmatch(r"[0-9]+-[0-9]+",ident) or now.tzinfo is None:
        raise ValueError("Invalid capture identity")
    parent=git(root,"rev-parse","HEAD").decode().strip()
    prior=previous(root)
    files=[]
    revisions=[]
    for path in selected(root):
        target=root/path
        if not target.is_file() or target.is_symlink():
            raise ValueError("Missing or unsafe snapshot file: "+path)
        data=target.read_bytes()
        files.append(record(path,data))
        if path.startswith(("engine/cache/macro/","engine/cache/series/","engine/cache/tv/")):
            # Compare with the checkout's prior committed bytes, not provider release time.
            old=subprocess.run(["git","show","HEAD:"+path],cwd=root,capture_output=True)
            delta=changes(path,old.stdout if old.returncode==0 else None,data)
            if delta and (delta["baseline_observations"] is not None or delta["changes"]):
                revisions.append({"path":path,**delta})
    manifest={"version":1,"id":ident,"captured_at":now.astimezone(dt.timezone.utc).isoformat(),
              "checkout_commit":parent,"previous":{"id":prior["id"],"sha256":digest(prior)} if prior else None,
              "files":files,"observation_changes":revisions,"policy":POLICY}
    return manifest

def public_summary(manifest):
    groups={}
    for r in manifest["files"]:
        p=r["path"]
        key="/".join(p.split("/")[:3]) if p.startswith("engine/cache/") else ("published_outputs" if p.startswith("site/") else "code_and_configuration")
        g=groups.setdefault(key,{"files":0,"bytes":0})
        g["files"]+=1;g["bytes"]+=r["bytes"]
    return {"version":1,"id":manifest["id"],"asof":manifest["captured_at"],"manifest_sha256":digest(manifest),
            "manifest_path":ARCHIVE+"/"+manifest["id"]+".json","checkout_commit":manifest["checkout_commit"],
            "groups":groups,"total_files":len(manifest["files"]),"total_bytes":sum(r["bytes"] for r in manifest["files"]),
            "changes":{k:sum(r[k] or 0 for r in manifest["observation_changes"]) for k in ("new_to_cache","revised","removed")},
            "baseline_series":sum(r["baseline_observations"] is not None for r in manifest["observation_changes"]),
            "previous":manifest["previous"],"policy":POLICY}

def check(root,manifest,commit=None):
    seen=set()
    for r in manifest["files"]:
        p=r["path"]
        if p in seen or p.startswith("/") or ".." in Path(p).parts:
            raise ValueError("Unsafe or duplicate manifest path")
        seen.add(p)
        data=git(root,"show",commit+":"+p) if commit else (root/p).read_bytes()
        if record(p,data)!=r:
            raise ValueError("Snapshot hash mismatch: "+p)
    if not set("site/data/"+p for p in OUTPUTS)<=seen:
        raise ValueError("Required outputs absent from manifest")
    if manifest["previous"]:
        p=manifest["previous"]
        old=read_json(root/ARCHIVE/(p["id"]+".json"))
        if digest(old)!=p["sha256"]:
            raise ValueError("Previous manifest changed")
    return []

def verify_commit(root=ROOT):
    doc=read_json(root/PUBLIC)
    manifest=read_json(root/doc["manifest_path"])
    if public_summary(manifest)!=doc:
        raise ValueError("Public provenance does not match archived manifest")
    check(root,manifest,"HEAD")
    # A run manifest is append-only on the normal branch, even though an
    # administrator could still rewrite history.
    status=git(root,"diff-tree","--no-commit-id","--name-status","-r","HEAD","--",ARCHIVE).decode().splitlines()
    if status!=["A\t"+doc["manifest_path"]]:
        raise ValueError("Expected exactly one newly added manifest")
    print("verified saved snapshot",doc["id"],doc["total_files"],"files")

def main():
    if sys.argv[1:]==["--verify-commit"]:
        verify_commit()
        return
    ident=capture_id()
    if ident is None:
        raise ValueError("Workflow run and attempt required")
    manifest=build(ROOT,ident,dt.datetime.now(dt.timezone.utc))
    path=ROOT/ARCHIVE/(ident+".json")
    if path.exists():
        raise ValueError("Capture already exists; use a distinct run attempt")
    check(ROOT,manifest)
    write(path,manifest)
    write(ROOT/PUBLIC,public_summary(manifest))
    print("captured",ident,len(manifest["files"]),"files")

if __name__=="__main__":
    main()
