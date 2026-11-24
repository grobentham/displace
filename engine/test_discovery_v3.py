"""Discovery v3: no false 'reversal' on coin flips, a range outcome that isn't circular, frozen snapshots."""
import copy
import datetime as dt
import json
import random

import discovery_v3 as V3

PLAN = json.loads(V3.PLAN.read_text())


def walk(seed, until=dt.date(2026, 11, 20), start=dt.date(2019, 6, 3)):
    rnd = random.Random(seed)
    rows, p, d = [], 100.0, start
    while d < until:
        if d.weekday() < 5:
            o = p
            c = p * (1 + rnd.gauss(0, 0.01))
            vol = abs(rnd.gauss(0, 0.006)) + 0.001
            rows.append((d.isoformat(), [o, max(o, c) * (1 + vol), min(o, c) * (1 - vol), c]))
            p = c
        d += dt.timedelta(days=1)
    return rows


def test_no_false_reversal_on_random_data():
    """v2's estimator flagged 'previous up' on every random walk; v3 must not."""
    flags = 0
    for seed in range(12):
        out = V3.run(PLAN, {m: walk(seed * 10 + i) for i, m in enumerate(PLAN["markets"])}, dt.date(2026, 11, 24))
        (b,) = out["batches"]
        assert b["kind"] == "historical" and len(b["results"]) == 128
        for r in b["results"]:
            if r["outcome"] == "next_positive_close" and r["status"] != "inconclusive":
                flags += 1
            if r["condition"] == "previous_up" and r["outcome"] == "next_positive_close":
                assert abs(r["effect"]) < 0.08, r["effect"]
    assert flags <= 2, flags                  # 12 x 64 direction tests at alpha/128: about 0.3 expected by chance


def test_range_outcome_is_against_a_normal_day():
    """With independent ranges, 'wide today' says nothing about tomorrow beating a normal day (v2 asked 'beating today')."""
    rows = walk(7)
    obs = V3.sample(rows)
    wide = [y["next_range_above_normal"] for _, f, y, _ in obs if f["wide_range"]]
    rest = [y["next_range_above_normal"] for _, f, y, _ in obs if not f["wide_range"]]
    assert abs(sum(wide) / len(wide) - sum(rest) / len(rest)) < 0.08


def test_frozen_and_prospective_rules():
    data = {m: walk(i, until=dt.date(2028, 12, 5)) for i, m in enumerate(PLAN["markets"])}
    first = V3.run(PLAN, data, dt.date(2026, 11, 24))
    assert [b["kind"] for b in first["batches"]] == ["historical"]
    assert all(r["status"] != "candidate_for_review" for r in first["batches"][0]["results"])   # history: never
    before = copy.deepcopy(first)
    later = V3.run(PLAN, data, dt.date(2028, 12, 2), first)
    assert later["batches"][0] == before["batches"][0]
    assert [(b["start"], b["end"]) for b in later["batches"][1:]] == [("2026-12-01", "2027-12-01"), ("2026-12-01", "2028-12-01")]
    for b in later["batches"][1:]:                # under 30 blocks: descriptive, so no candidate yet
        assert all(r["status"] in ("descriptive_only", "insufficient_data", "inconclusive") for r in b["results"])
    try:
        V3.run(dict(PLAN, alpha=0.1), data, dt.date(2026, 11, 24), first)
        raise AssertionError("a changed plan must be refused")
    except ValueError:
        pass


if __name__ == "__main__":
    test_no_false_reversal_on_random_data()
    test_range_outcome_is_against_a_normal_day()
    test_frozen_and_prospective_rules()
    print("discovery v3 tests passed")
