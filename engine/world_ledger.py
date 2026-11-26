"""Displace World ledger: signals, frozen claims, assessments and corrections.

The ledger is the product. Every page in Displace World is a view of these files:

  site/data/world/ledger/signals-YYYY-MM.json   signals published that month (never rewritten)
  site/data/world/ledger/claims.json            every claim, frozen at publication with a SHA-256 hash
  site/data/world/ledger/assessments.json       the grading history of each claim (newest last)
  engine/world/corrections.json                 corrections entered by hand (copied to the ledger folder)

Rules the code enforces:
  - a frozen claim can never change: saving a claim whose hash differs from the stored one raises FrozenError
  - a signal, once written, is never edited; corrections are separate records that point at it
  - an assessment is only ever appended; the latest one is the current label
  - grading uses the rule stored in the claim, never a judgement made later
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "site/data/world/ledger"
CORRECTIONS = ROOT / "engine/world/corrections.json"

LABELS = ("hit", "miss", "unresolved", "not_assessable")
KINDS = ("forecast", "checkpoint")
CLASSES = ("fact", "interpretation", "estimate", "open_question")
FROZEN = ("id", "signal_id", "statement", "kind", "rule", "due", "probability", "base", "frozen_at")


class FrozenError(ValueError):
    """A frozen record would have been changed."""


def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def claim_hash(c):
    return digest({k: c.get(k) for k in FROZEN})


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path, obj, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        if compact:
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        else:
            json.dump(obj, fh, ensure_ascii=False, indent=1, allow_nan=False)
        fh.write("\n")
    os.replace(tmp, path)


class Ledger:
    def __init__(self, root=LEDGER, corrections=CORRECTIONS):
        self.root = Path(root)
        self.corrections_path = Path(corrections)
        self.signals = {}          # id -> signal
        self.claims = {}           # id -> claim
        self.assessments = {}      # claim id -> [assessment, ...]
        self.new_signal_ids = []
        self._months = set()
        self.load()

    # loading -----------------------------------------------------------------------------------------------
    def load(self):
        for path in sorted(self.root.glob("signals-*.json")):
            for s in load_json(path, {}).get("signals", []):
                self.signals[s["id"]] = s
        for c in load_json(self.root / "claims.json", {}).get("claims", []):
            if c.get("hash") != claim_hash(c):
                raise FrozenError("Stored claim does not match its hash: " + c["id"])
            self.claims[c["id"]] = c
        self.assessments = load_json(self.root / "assessments.json", {}).get("assessments", {})

    def corrections(self):
        return load_json(self.corrections_path, {"corrections": []}).get("corrections", [])

    # writing -----------------------------------------------------------------------------------------------
    def add_signal(self, signal, claims):
        """Publish a signal with its claims. Returns False when the signal id already exists."""
        if signal["id"] in self.signals:
            return False
        problems = check_signal(signal)
        if problems:
            raise ValueError(signal["id"] + ": " + "; ".join(problems))
        ids = []
        for c in claims:
            c = dict(c)
            c["signal_id"] = signal["id"]
            c.setdefault("frozen_at", signal["published_at"])
            c["hash"] = claim_hash(c)
            problems = check_claim(c)
            if problems:
                raise ValueError(c["id"] + ": " + "; ".join(problems))
            old = self.claims.get(c["id"])
            if old and old["hash"] != c["hash"]:
                raise FrozenError("Claim already frozen with different content: " + c["id"])
            self.claims[c["id"]] = c
            ids.append(c["id"])
        signal = dict(signal, claims=ids)
        self.signals[signal["id"]] = signal
        self.new_signal_ids.append(signal["id"])
        self._months.add(signal["published_at"][:7])
        return True

    def assess(self, claim_id, label, observed, happened, now, learned="", still_open=""):
        """Append a grade when it differs from the current one. Hits and misses are final."""
        if label not in LABELS:
            raise ValueError("Unknown label " + label)
        history = self.assessments.setdefault(claim_id, [])
        if history and history[-1]["label"] in ("hit", "miss", "not_assessable"):
            return False
        if history and history[-1]["label"] == label and history[-1].get("observed") == observed:
            return False
        history.append({"label": label, "assessed_at": iso(now), "observed": observed, "happened": happened,
                        "learned": learned, "open": still_open})
        return True

    def current(self, claim_id):
        history = self.assessments.get(claim_id) or []
        label = history[-1]["label"] if history else "unresolved"
        for c in self.corrections():
            if c.get("target") == claim_id and c.get("label") in LABELS:
                label = c["label"]
        return label

    def save(self):
        # Re-read what is on disk and refuse to change anything frozen there.
        disk = {c["id"]: c for c in load_json(self.root / "claims.json", {}).get("claims", [])}
        for cid, c in disk.items():
            if cid not in self.claims or self.claims[cid]["hash"] != c["hash"]:
                raise FrozenError("A stored claim was removed or changed: " + cid)
        months = {}
        for s in self.signals.values():
            months.setdefault(s["published_at"][:7], []).append(s)
        for month, rows in months.items():
            path = self.root / f"signals-{month}.json"
            stored = {s["id"]: s for s in load_json(path, {}).get("signals", [])}
            for sid, s in stored.items():
                if digest(s) != digest(self.signals.get(sid, {})):
                    raise FrozenError("A published signal was changed: " + sid)
            if month in self._months or not path.exists():
                rows.sort(key=lambda s: (s["published_at"], s["id"]))
                write_json(path, {"month": month, "signals": rows}, compact=True)
        write_json(self.root / "claims.json",
                   {"claims": sorted(self.claims.values(), key=lambda c: (c["frozen_at"], c["id"]))}, compact=True)
        write_json(self.root / "assessments.json", {"assessments": dict(sorted(self.assessments.items()))},
                   compact=True)
        write_json(self.root / "corrections.json", {"corrections": self.corrections()})


# validation ---------------------------------------------------------------------------------------------------
def check_signal(s):
    p = []
    for k in ("id", "kind", "category", "title", "published_at", "facts", "sources"):
        if not s.get(k):
            p.append("missing " + k)
    for line in s.get("facts", []) + s.get("why", []) + s.get("counter", []) + s.get("next", []):
        if line.get("class") not in CLASSES or not line.get("text"):
            p.append("statement without a valid class")
            break
    for src in s.get("sources", []):
        if not str(src.get("url", "")).startswith(("https://", "http://")):
            p.append("source without a URL")
            break
    return p


def check_claim(c):
    p = []
    if c.get("kind") not in KINDS:
        p.append("bad kind")
    if not c.get("statement") or not isinstance(c.get("rule"), dict) or not c["rule"].get("type"):
        p.append("claim needs a statement and a rule")
    try:
        dt.date.fromisoformat(str(c.get("due"))[:10])
    except ValueError:
        p.append("claim needs a due date")
    prob = c.get("probability")
    if prob is not None and not (type(prob) in (int, float) and 0 < prob < 1):
        p.append("probability must be between 0 and 1")
    if prob is not None and not (isinstance(c.get("base"), dict) and c["base"].get("n", 0) >= 20):
        p.append("a probability needs a historical base of at least 20 cases")
    return p
