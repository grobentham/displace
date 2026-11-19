"""Tests for keyless sources and the official-news digest."""
import datetime as dt
import unittest
from unittest.mock import patch

import agencies
import engine
import news
import publicdata
import quality
import source_health


class PublicDataTests(unittest.TestCase):
    def test_source_checks_keep_last_success_and_track_fallbacks_independently(self):
        initial = "2026-11-17T08:00-05:00"
        later = "2026-11-18T08:00-05:00"
        with (
            patch.object(source_health, "CHECKS", {}),
            patch.object(publicdata, "FRED_AVAILABLE", True),
            patch.object(publicdata, "ALFRED_AVAILABLE", True),
        ):
            source_health.record("fred", True)
            source_health.record("census", True)
            before = source_health.snapshot({}, initial)
            source_health.CHECKS.clear()
            with patch.object(publicdata, "download", side_effect=OSError("fixture offline")):
                publicdata.check_fred_access(dt.date(2026, 11, 18))
            source_health.record("bea", True)
            source_health.record("treasury", True)
            source_health.record("treasury", False)
            after = source_health.snapshot(before, later)
        self.assertEqual(after["fred"], {"state": "unavailable", "checkedAt": later, "lastSuccessAt": initial})
        self.assertEqual(after["alfred"]["state"], "unavailable")
        self.assertEqual(after["bea"], {"state": "available", "checkedAt": later, "lastSuccessAt": later})
        self.assertEqual(after["treasury"]["state"], "partial")
        self.assertEqual(after["census"], {"state": "not_checked", "checkedAt": initial, "lastSuccessAt": initial})

    def test_release_calendar_skips_undated_and_unrelated_rows(self):
        parser = publicdata.ReleaseCalendar(10)
        parser.feed("""
        <tr><td><span>Tuesday November 10, 2026</span><span>Updated</span></td></tr>
        <tr><td>7:30 am</td><td><a href="/release?rid=10">CPI</a></td></tr>
        <tr><td>Wednesday November 11, 2026</td></tr>
        <tr><td>N/A</td><td><a href="/release?rid=10">CPI</a></td></tr>
        <tr><td>7:30 am</td><td><a href="/release?rid=46">PPI</a></td></tr>
        """)
        self.assertEqual(parser.dates, {"2026-11-10"})

    def test_csv_requires_the_requested_vintage(self):
        body = b"observation_date,CPI_20261110\n2026-09-01,102\n2026-10-01,.\n"
        self.assertEqual(
            publicdata.read_csv(body, "CPI_20261110", "2026-01-01", "2026-11-10"),
            [("2026-09-01", 102.0, "2026-11-10")],
        )
        with self.assertRaises(ValueError):
            publicdata.read_csv(body, "CPI_20261109", "2026-01-01")

    def test_bea_preserves_the_reported_period_and_eastern_time(self):
        body = (b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
                b"SUMMARY:Personal Income and Outlays\\, December 2026\r\n"
                b"DTSTART:20270128T133000Z\r\nEND:VEVENT\r\nEND:VCALENDAR")
        kind, released, period, _ = list(publicdata.parse_bea_calendar(body, engine.NY))[0]
        self.assertEqual((kind, released.isoformat(), period), ("pce", "2027-01-28T08:30:00-05:00", "Dec"))

    def test_release_must_appear_in_the_post_release_snapshot(self):
        event = {"title": "CPI inflation (Oct)", "date": "2026-11-10"}
        before = [("2026-08-01", 100, "2026-11-09"), ("2026-09-01", 101, "2026-11-09")]
        after = [("2026-08-01", 100, "2026-11-10"), ("2026-09-01", 101, "2026-11-10"),
                 ("2026-10-01", 102, "2026-11-10")]
        with patch.object(engine, "TODAY", dt.date(2026, 11, 10)):
            with patch.object(publicdata, "observations", side_effect=[before, after]):
                actual, previous, rows = engine.public_figures(event, "cpi", "CPILFESL", "pct", True)
            self.assertEqual((actual, previous, rows[-1][2]), ("1.0%", "1.0%", "2026-11-10"))
            with patch.object(publicdata, "observations", side_effect=[after, after]):
                self.assertIsNone(engine.public_figures(event, "cpi", "CPILFESL", "pct", True)[0])
            with patch.object(publicdata, "observations", return_value=after):
                self.assertIsNone(engine.public_figures(event, "cpi", "CPILFESL", "pct", False)[0])
            with patch.object(publicdata, "observations", side_effect=[None, after]):
                self.assertIsNone(engine.public_figures(event, "cpi", "CPILFESL", "pct", True)[0])

    def test_payrolls_and_claims_use_the_same_units_in_text_and_quality_checks(self):
        self.assertEqual(engine.fmt("diffPersons", 86000), "86K")
        history = [188000 + 1000 * i for i in range(16)]
        report = quality.Report()
        result = quality.gate_figure(report, "weekly", "Claims", "ICSA", "claims", "200K", history, {}, "run")
        self.assertEqual(result, "publish")

    def test_census_report_matches_release_date_and_period(self):
        body = (b"FOR IMMEDIATE RELEASE: Tuesday, November 17, 2026 "
                b"Advance estimates of U.S. retail and food services sales for October 2026, "
                b"adjusted for seasonal variation, were $748.2 billion, up 0.2 percent "
                b"(&plusmn;0.4 percent)* from the previous month.")
        reading = agencies.retail_from_page(body)
        event = {"title": "Retail sales (Oct)", "date": "2026-11-17"}
        with patch.object(agencies, "retail", return_value=reading):
            actual, _, _, source = engine.agency_figures(event, "retail", "RSAFS", "pct", True)
            self.assertEqual((actual, source["published"]), ("0.2%", "2026-11-17"))
            event["date"] = "2026-11-16"
            self.assertIsNone(engine.agency_figures(event, "retail", "RSAFS", "pct", True)[0])

    def test_bea_headlines_distinguish_the_monthly_core_inflation_reading(self):
        body = (b"EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Thursday, October 29, 2026 "
                b"Personal Income and Outlays, September 2026. From the preceding month, "
                b"the PCE price index for September increased 0.5 percent. Excluding food and energy, "
                b"the PCE price index increased 0.3 percent. From the same month one year ago, "
                b"the PCE price index increased 3.6 percent.")
        published, period, _, values = agencies.parse_bea_report("pce", body)
        self.assertEqual((str(published), str(period), values["PCEPILFE"]), ("2026-10-29", "2026-09-01", 0.3))


class NewsDigestTests(unittest.TestCase):
    def test_news_uses_official_links_and_preserves_data_on_outage(self):
        feed = b"""<rss><channel>
        <item><title>Federal Reserve issues FOMC statement</title>
          <link>https://www.federalreserve.gov/news.htm</link>
          <pubDate>Wed, 28 Oct 2026 18:00:00 GMT</pubDate></item>
        <item><title>Federal Reserve issues FOMC statement</title>
          <link>https://example.com/news.htm</link>
          <pubDate>Wed, 28 Oct 2026 18:00:00 GMT</pubDate></item>
        </channel></rss>"""
        statement = b"<p>The Committee decided to maintain the target range for the federal funds rate at 3-3/4 to 4 percent.</p>"
        now = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)

        def fetch(url):
            if url == news.FEEDS["Federal Reserve"]:
                return feed
            if url == "https://www.federalreserve.gov/news.htm":
                return statement
            raise OSError("fixture offline")

        first = news.build([], {}, now, fetch=fetch, log=lambda *_: None)
        self.assertEqual(len(first["items"]), 1)
        self.assertIn("3-3/4% to 4%", first["items"][0]["analysis"])

        def offline(_url):
            raise OSError("temporary outage")

        same = news.build([], first, now + dt.timedelta(days=1), fetch=offline, log=lambda *_: None)
        self.assertEqual(same["items"], first["items"])
        self.assertFalse(same["sources"]["Federal Reserve"])
        self.assertEqual(same["sourceHealth"]["Federal Reserve"], {
            "state": "unavailable", "checkedAt": news.timestamp(now + dt.timedelta(days=1)),
            "lastSuccessAt": first["checkedAt"],
        })


    def test_fomc_minutes_key_points(self):
        body = ("Staff saw risks. Participants noted that upside risks to inflation had increased. "
                "With regard to the outlook for monetary policy in the months ahead, almost all participants judged that "
                "further action\u2014broadly consistent with the projections\u2014would likely be appropriate. A couple disagreed. "
                "Committee Policy Actions Members agreed. Voting against this action: Lisa D. Cook and Beth M. Hammack, "
                "who preferred to raise the target range. Consistent with")
        pages = {"https://www.federalreserve.gov/m.htm": b'<a href="/monetarypolicy/fomcminutes20261028.htm">',
                 "https://www.federalreserve.gov/monetarypolicy/fomcminutes20261028.htm": body.encode()}
        out = news.policy_summary("minutes", "Minutes", "https://www.federalreserve.gov/m.htm", pages.__getitem__)
        self.assertIn("further action would likely be appropriate", out)
        self.assertIn("upside risks to inflation", out)
        self.assertIn("Dissent: Lisa D. Cook and Beth M. Hammack, who preferred to raise the target range.", out)
        unanimous = body.replace("Lisa D. Cook and Beth M. Hammack, who preferred to raise the target range", "None")
        pages["https://www.federalreserve.gov/monetarypolicy/fomcminutes20261028.htm"] = unanimous.encode()
        self.assertIn("unanimous", news.policy_summary("minutes", "M", "https://www.federalreserve.gov/m.htm", pages.__getitem__))

if __name__ == "__main__":
    unittest.main()
