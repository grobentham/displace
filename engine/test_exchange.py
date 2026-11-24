"""CME sessions: holidays, halts, early closes, daylight saving, settlement and forecast targets."""
import datetime as dt

import exchange as X

NY = X.NY
D = dt.date


def at(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=NY)


def test_2026_calendar():
    cal = {d.isoformat(): v[0] for d, v in X.calendar(2026).items()}
    assert cal == {"2026-01-01": "closed", "2026-04-03": "closed", "2026-12-25": "closed",
                   "2026-01-19": "halt", "2026-02-16": "halt", "2026-05-25": "halt", "2026-06-19": "halt",
                   "2026-07-03": "halt", "2026-09-07": "halt", "2026-11-26": "halt",
                   "2026-11-27": "early", "2026-12-24": "early"}, cal
    assert X.calendar(2021).get(D(2021, 6, 18)) is None                  # Juneteenth only from 2022
    assert X.calendar(2027)[D(2027, 12, 24)][0] == "closed"              # Christmas on a Saturday: Friday off
    assert X.calendar(2023)[D(2023, 1, 2)][0] == "closed"                # New Year on a Sunday: Monday off


def test_thanksgiving_week():
    assert not X.is_trade_date("2026-11-26") and X.next_trade_date("2026-11-25") == D(2026, 11, 27)
    s = X.session("nq", "2026-11-27")
    assert s["open"] == at("2026-11-25T18:00") and s["early_close"]       # opens Wednesday evening
    assert s["close"] == at("2026-11-27T13:15") and s["settle"] == at("2026-11-27T13:00")
    assert s["includes_halt_days"][0]["date"] == "2026-11-26" and s["includes_halt_days"][0]["halt_at"].startswith("2026-11-26T13:00")
    g = X.session("gold", "2026-11-27")
    assert g["close"] is None and g["settle"] == at("2026-11-27T13:30")   # metals: CME announces the close
    assert X.session_for("nq", at("2026-11-26T10:00")) == D(2026, 11, 27)  # holiday morning trades for Friday
    assert X.session_for("nq", at("2026-11-26T14:00")) is None            # halted after 13:00
    assert X.session_for("nq", at("2026-11-26T19:00")) == D(2026, 11, 27)


def test_weekends_closures_and_daily_break():
    assert X.session("nq", "2026-11-30")["open"] == at("2026-11-29T18:00")          # Monday opens Sunday
    assert X.session("nq", "2026-04-06")["open"] == at("2026-04-05T18:00")          # after Good Friday
    assert X.session("nq", "2026-12-28")["open"] == at("2026-12-27T18:00")          # after Christmas
    assert X.session("nq", "2026-01-20")["open"] == at("2026-01-18T18:00")          # Tuesday after MLK: from Sunday
    assert X.session_for("nq", at("2026-11-24T17:30")) is None                      # daily break
    assert X.session_for("nq", at("2026-11-24T18:05")) == D(2026, 11, 25)
    assert X.session_for("nq", at("2026-11-28T12:00")) is None                      # Saturday
    assert X.session("nq", "2026-11-26") is None


def test_daylight_saving():
    """Sessions keep New York clock times; the UTC times move with daylight saving (8 Mar and 1 Nov 2026)."""
    utc = dt.timezone.utc
    before = X.session("nq", "2026-03-06")["open"].astimezone(utc)        # Thu 5 Mar 18:00 EST
    after = X.session("nq", "2026-03-10")["open"].astimezone(utc)         # Mon 9 Mar 18:00 EDT
    assert before.hour == 23 and after.hour == 22
    assert X.session("nq", "2026-03-09")["open"].astimezone(utc) == dt.datetime(2026, 3, 8, 22, tzinfo=utc)
    assert X.session("nq", "2026-11-02")["open"].astimezone(utc) == dt.datetime(2026, 11, 1, 23, tzinfo=utc)


def test_settlement_by_market():
    t = {m: X.session(m, "2026-11-24")["settle"].strftime("%H:%M") for m in X.GROUP}
    assert t == {"nq": "16:00", "es": "16:00", "ym": "16:00", "rty": "16:00", "gold": "13:30", "cl": "14:30",
                 "6e": "15:00", "btc": "16:00"}, t


def test_forecast_targets():
    """A forecast must be for the first session that hasn't opened yet."""
    assert X.target_for("nq", at("2026-11-24T17:42")) == D(2026, 11, 25)
    assert X.target_for("nq", at("2026-11-24T18:42")) == D(2026, 11, 26 + 1)    # Wednesday's session is open
    assert X.target_for("nq", at("2026-11-25T17:42")) == D(2026, 11, 27)        # Friday opens Wednesday 18:00
    assert X.target_for("nq", at("2026-11-25T18:30")) == D(2026, 11, 30)        # ...and once it has, Monday
    assert X.target_for("nq", at("2026-11-27T17:42")) == D(2026, 11, 30)


def test_holiday_candles_fold_into_the_next_session():
    """bias.clean: Yahoo's Memorial Day candle (a short session until the 13:00 halt) joins Tuesday's."""
    import bias as B
    rows = [("2026-05-22", [100.0, 102.0, 99.0, 101.0]), ("2026-05-25", [101.0, 101.5, 100.5, 101.2]),
            ("2026-05-26", [101.3, 104.0, 100.8, 103.0]), ("2026-05-27", [103.0, 103.5, 101.0, 102.0])]
    out = B.clean("nq", rows)
    assert [d for d, _ in out] == ["2026-05-22", "2026-05-26", "2026-05-27"]
    assert out[1][1] == [101.0, 104.0, 100.5, 103.0]
    assert B.clean("nq", rows[:2]) == rows[:1]                   # a holiday candle with nothing after it is dropped


if __name__ == "__main__":
    test_2026_calendar()
    test_thanksgiving_week()
    test_weekends_closures_and_daily_break()
    test_daylight_saving()
    test_settlement_by_market()
    test_forecast_targets()
    test_holiday_candles_fold_into_the_next_session()
    print("exchange tests passed")
