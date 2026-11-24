"""Run one engine step, record how it went, and never stop the publish job.

    python engine/guard.py NAME script.py [args...]

Each step's result goes to site/data/engine/health.json (state ok / failed, exit code, seconds, the last lines of
its output when it failed). The job carries on either way, so one broken engine can't stop the others or the
deploy, and the last good files stay live. engine/gate.py then validates every output and, at the very end of the
run, turns the job red if any step failed: a failure is visible in GitHub instead of hiding behind a green tick.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HEALTH = os.path.join(os.path.dirname(HERE), "site", "data", "engine", "health.json")


def run_id():
    return os.environ.get("GITHUB_RUN_ID") or "local"


def load(path=None):
    try:
        return json.load(open(path or HEALTH))
    except (OSError, ValueError):
        return {"components": {}}


def save(doc, path=None):
    path = path or HEALTH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def mark(name, state, note="", rc=None, seconds=None, path=None):
    doc = load(path)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    prev = doc["components"].get(name, {})
    rec = {"state": state, "at": now, "run": run_id(), "rc": rc, "seconds": seconds, "note": note[-1500:]}
    rec["lastOk"] = now if state == "ok" else prev.get("lastOk")
    doc["components"][name] = rec
    doc["updated"] = now
    save(doc, path)
    return rec


def main(argv):
    name, cmd = argv[1], argv[2:]
    t0 = time.time()
    p = subprocess.run([sys.executable, "-u", *cmd], cwd=os.path.dirname(HERE), capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    secs = round(time.time() - t0, 1)
    tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-12:])
    rec = mark(name, "ok" if p.returncode == 0 else "failed", "" if p.returncode == 0 else tail, p.returncode, secs)
    print(f"guard: {name} {rec['state']} (exit {p.returncode}, {secs}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
