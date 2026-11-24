"""Regression tests for the Phase 1 integrity fixes (24 Nov 2026): invalid forecasts are voided but kept, late
forecasts don't count, the log archives instead of dropping, a crash is reported instead of hidden, and the final
check restores invalid outputs."""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bias as B  # noqa: E402
import gate as GT  # noqa: E402
import guard as G  # noqa: E402

NY = B.NY


def entry(**kw):
    e = {"market": "nq", "candle": "2026-11-19", "for": "2026-11-20", "bias": "long", "p_up": 0.54, "base_up": 0.54,
         "tier": "base", "p_high": 0.5, "p_low": 0.5, "range_lo": 400.0, "range_hi": 1300.0, "up1": 27000.0, "dn1": 26000.0,
         "p_up1": 0.3, "p_dn1": 0.3, "logged": "2026-11-19T17:30-05:00"}
    e.update(kw)
    return e


def test_negative_range_is_voided_not_deleted():
    """20 Nov 2026: NQ and gold were logged with ranges of -27,278 to -26,546 and scored as misses."""
    bad = entry(range_lo=-27278.86, range_hi=-26546.49, scored=1, inRange=0)
    good = entry(market="gold")
    es = B.audit([bad, good], dt.datetime(2026, 11, 24, 9, 0, tzinfo=dt.timezone.utc))
    assert len(es) == 2 and es[0]["void"] and "not a valid high-minus-low range" in es[0]["correction"]["reason"]
    assert es[0]["range_lo"] == -27278.86 and es[0]["inRange"] == 0       # the original stays as published
    assert not good.get("void")
    s = B.summary(es)
    assert s["voided"] == 1 and s["days"] == 0                            # unscored good entry; the void one never counts
    assert B.score_log({}, [entry(void=True)])[0].get("scored") is None   # a void entry is never scored


def test_bad_probabilities_and_levels():
    assert B.problems(entry(p_up=1.2)) and B.problems(entry(p_high=float("nan")))
    assert B.problems(entry(up1=26000.0, dn1=27000.0)) and B.problems(entry(range_lo=900.0, range_hi=800.0))
    assert not B.problems(entry())


def test_eligibility():
    """A forecast counts only if it was issued before its futures session opened (18:00 New York the evening before)."""
    assert B.window_start("2026-11-23") == dt.datetime(2026, 11, 22, 18, 0, tzinfo=NY)        # Monday: Sunday 18:00
    early, late = entry(logged="2026-11-19T17:42-05:00"), entry(logged="2026-11-20T05:16-05:00", market="es")
    B.audit([early, late], dt.datetime(2026, 11, 24, tzinfo=dt.timezone.utc))
    assert early["eligible"] is True and late["eligible"] is False
    late.update(scored=1, up=1, brier=0.2, inRange=1, highTaken=1, lowTaken=0)
    s = B.summary([late])
    assert s["days"] == 0 and s["late"] == 1


def test_archive_keeps_everything():
    with tempfile.TemporaryDirectory() as d:
        es = [entry(candle=f"2025-{m:02d}-01", **{"for": f"2025-{m:02d}-02"}) for m in range(1, 7)]
        live = B.archive(es, keep=2, directory=d)
        assert [e["candle"] for e in live] == ["2025-05-01", "2025-06-01"]
        a = json.load(open(os.path.join(d, "log-2025.json")))["entries"]
        assert len(a) == 4
        B.archive(es, keep=2, directory=d)                                 # a second run adds no duplicates
        assert len(json.load(open(os.path.join(d, "log-2025.json")))["entries"]) == 4


def test_gate_checks_bias_output():
    ok = {"markets": {"nq": {"p_up": 0.54, "base_up": 0.54, "takes": {"high": {"p": 0.6}, "low": {"p": 0.1}},
                             "range": {"lo": 400.0, "points": 800.0, "hi": 1300.0}, "levels": {"high": 2.0, "low": 1.0}}}}
    assert GT.check_bias(ok) == []
    bad = json.loads(json.dumps(ok))
    bad["markets"]["nq"]["range"] = {"lo": -27278.0, "points": -26900.0, "hi": -26546.0}
    bad["markets"]["nq"]["p_up"] = 1.4
    msgs = GT.check_bias(bad)
    assert any("range" in m for m in msgs) and any("p_up" in m for m in msgs)
    assert GT.check_log({"entries": [entry(), entry()]}) == ["duplicate forecast ('nq', '2026-11-19')"]
    assert GT.check_log({"entries": [entry(range_lo=-1.0, range_hi=5.0, void=True)]}) == []


def test_gate_restores_invalid_files():
    with tempfile.TemporaryDirectory() as root:
        data = os.path.join(root, "site", "data")
        os.makedirs(os.path.join(data, "bias"))
        good = {"markets": {}}
        path = os.path.join(data, "bias", "current.json")
        json.dump(good, open(path, "w"))
        git = lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True, check=True)
        git("init", "-q")
        git("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "good")
        open(path, "w").write('{"markets": {"nq": ')                       # a crash half-way through a write
        open(os.path.join(data, "bias", "log.json.tmp"), "w").write("partial")
        real = (GT.ROOT, G.HEALTH)
        GT.ROOT, G.HEALTH = root, os.path.join(data, "engine", "health.json")
        try:
            os.environ["GITHUB_RUN_ID"] = "t1"
            f = GT.validate(data, fix=True)
            assert list(f) == [os.path.join("bias", "current.json")]
            assert json.load(open(path)) == good                              # last good version is back
            assert not os.path.exists(os.path.join(data, "bias", "log.json.tmp"))
            h = json.load(open(G.HEALTH))["components"]
            assert h["gate"]["state"] == "failed" and "restored" in h["output:" + os.path.join("bias", "current.json")]["note"]
        finally:
            GT.ROOT, G.HEALTH = real
            os.environ.pop("GITHUB_RUN_ID", None)


def test_guard_reports_a_crash_and_carries_on():
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "boom.py")
        open(script, "w").write("import sys\nprint('working')\nraise SystemExit(3)\n")
        real = G.HEALTH
        G.HEALTH = os.path.join(d, "health.json")
        try:
            os.environ["GITHUB_RUN_ID"] = "t2"
            assert G.main(["guard.py", "boomer", script]) == 0                 # the job goes on
            rec = json.load(open(G.HEALTH))["components"]["boomer"]
            assert rec["state"] == "failed" and rec["rc"] == 3 and "working" in rec["note"]
            assert GT.report() == 1                                            # and the run ends red
            G.mark("boomer", "ok")
            assert GT.report() == 0
        finally:
            G.HEALTH = real
            os.environ.pop("GITHUB_RUN_ID", None)


if __name__ == "__main__":
    test_negative_range_is_voided_not_deleted()
    test_bad_probabilities_and_levels()
    test_eligibility()
    test_archive_keeps_everything()
    test_gate_checks_bias_output()
    test_gate_restores_invalid_files()
    test_guard_reports_a_crash_and_carries_on()
    print("gate tests passed")
