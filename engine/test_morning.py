import datetime as dt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from morning import SGT, build_edition, edition_time, market_outlook, publish, scheduled_earnings
from engine import load
from earnings_news import report_items, report_summary


def time(value):
    return dt.datetime.fromisoformat(value)


class MorningTests(unittest.TestCase):
    def test_preparation_and_weekend_rollover(self):
        before = time("2026-11-20T22:39:59+00:00")
        prepare = time("2026-11-20T22:40:00+00:00")
        self.assertEqual(edition_time(before).isoformat(), "2026-11-20T07:00:00+08:00")
        self.assertEqual(edition_time(prepare).isoformat(), "2026-11-21T07:00:00+08:00")

    def test_news_cutoff_and_singapore_schedule(self):
        opens = time("2026-11-18T07:00:00+08:00")
        now = time("2026-11-18T06:44:00+08:00")
        calendar = {"through": "2026-11-20", "events": [
            {"date": "2026-11-17", "time": "08:30", "title": "Retail sales", "cur": "USD", "impact": "high"},
            {"date": "2026-11-18", "time": "14:00", "title": "FOMC minutes", "cur": "USD", "impact": "medium"},
            {"date": "2026-11-18", "time": "18:00", "title": "After the brief's window", "cur": "USD", "impact": "high"},
        ]}
        news = {"checkedAt": "2026-11-17T22:43:00+00:00", "items": [
            {"title": "Reported retail sales", "published": "2026-11-17T13:30:00+00:00", "url": "https://example.com/retail"},
            {"title": "After preparation", "published": "2026-11-17T22:50:00+00:00", "url": "https://example.com/future"},
            {"title": "Older than a day", "published": "2026-11-16T22:59:00+00:00", "url": "https://example.com/older"},
        ]}
        brief = build_edition(opens, now, calendar, news, {})
        self.assertEqual(brief["upcoming"], [{"at": "2026-11-19T03:00+08:00", "title": "FOMC minutes"}])
        self.assertEqual([item["title"] for item in brief["updates"]], ["Reported retail sales"])
        self.assertEqual(brief["focus"]["title"], "FOMC minutes")
        self.assertTrue(brief["calendarCovered"])
        self.assertTrue(brief["feedsChecked"])

    def test_publishing_retains_both_editions_and_is_idempotent(self):
        with TemporaryDirectory() as directory:
            data = Path(directory)
            target = data / "brief" / "morning.json"
            def no_reports(start, cutoff):
                return [], 6
            publish(dt.datetime(2026, 11, 20, 8, tzinfo=SGT), data, no_reports)
            publish(dt.datetime(2026, 11, 21, 6, 42, tzinfo=SGT), data, no_reports)
            first = target.read_bytes()
            publish(dt.datetime(2026, 11, 21, 10, tzinfo=SGT), data, no_reports)
            self.assertEqual(target.read_bytes(), first)
            self.assertEqual([item["date"] for item in load(target, {})["editions"]], ["2026-11-21", "2026-11-20"])

    def test_outlook_requires_both_yields_from_the_expected_session(self):
        opens = time("2026-11-18T07:00+08:00")
        def markets(short, long, day="2026-11-17"):
            return {"tiles": {"y2": {"d1": short, "date": day}, "y10": {"d1": long, "date": day}}}
        self.assertEqual(market_outlook(opens, markets(-3, -5))["label"], "Bullish tilt")
        self.assertEqual(market_outlook(opens, markets(4, 3))["label"], "Bearish tilt")
        self.assertEqual(market_outlook(opens, markets(-3, 3))["label"], "Neutral")
        self.assertEqual(market_outlook(opens, markets(-3, -2))["label"], "Neutral")
        self.assertEqual(market_outlook(opens, markets(-3, -5, "2026-11-16"))["label"], "Data pending")
        self.assertEqual(market_outlook(time("2026-11-21T07:00+08:00"), {})["label"], "No U.S. session")

    def test_scheduled_earnings_keep_session_labels_without_fabricating_a_time(self):
        opens = time("2026-11-18T07:00+08:00")
        events = [{"id": "20261118-earn-panw", "date": "2026-11-18", "time": "16:05", "session": "AMC"},
                  {"id": "20261119-earn-wmt", "date": "2026-11-19", "time": "07:00", "session": "BMO"},
                  {"id": "20261118-earn-amzn", "date": "2026-11-18", "time": "", "session": ""}]
        rows = scheduled_earnings(opens, opens + dt.timedelta(days=1), {"events": events})
        self.assertEqual([row["symbol"] for row in rows], ["AMZN", "PANW"])
        self.assertNotIn("at", rows[0])
        self.assertEqual(rows[1]["at"], "2026-11-19T05:05+08:00")
        self.assertFalse(rows[1]["timeConfirmed"])

    def test_issuer_results_are_distinct_from_event_notices(self):
        feed = b"""<rss><channel>
          <item><title>Issuer to Announce Third Quarter Results</title>
          <link>https://example.com/event</link><pubDate>Tue, 17 Nov 2026 16:20:00 -0500</pubDate></item>
          <item><title>Issuer Reports Third Quarter Results</title>
          <link>https://example.com/report</link><pubDate>Tue, 17 Nov 2026 16:20:00 -0500</pubDate></item>
          </channel></rss>"""
        rows = list(report_items(feed, "https://example.com/feed", time("2026-11-17T00:00+00:00"), time("2026-11-17T23:00+00:00")))
        self.assertEqual([row[2] for row in rows], ["https://example.com/report"])
        self.assertEqual(list(report_items(feed, "https://example.com/feed", time("2026-11-17T00:00+00:00"), time("2026-11-17T21:00+00:00"))), [])
        summary = report_summary(b"Issuer reported revenue for the third quarter of $12.3 billion, up 9% from a year ago. "
                                 b"GAAP and non-GAAP earnings per diluted share were $1.25 and $1.40, respectively. "
                                 b"The outlook for the fourth quarter is as follows: Revenue is expected to be $14 billion, plus or minus 2%.")
        self.assertEqual(summary, "Revenue $12.3 billion (up 9% year over year). GAAP diluted EPS $1.25. "
                                  "Next-quarter revenue guidance $14 billion \u00b12%.")


if __name__ == "__main__":
    unittest.main()
