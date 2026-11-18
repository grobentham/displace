import datetime as dt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from morning import SGT, build_edition, edition_time, market_outlook, publish, refresh_edition, scheduled_earnings
from engine import load
from earnings_news import report_items, report_metrics, report_summary


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
        self.assertEqual(brief["upcoming"][0]["at"], "2026-11-19T03:00+08:00")
        self.assertIn("disagreement", brief["upcoming"][0]["watch"])
        self.assertEqual([item["title"] for item in brief["updates"]], ["Reported retail sales"])
        self.assertEqual(brief["focus"]["title"], "FOMC minutes")
        self.assertEqual(brief["focus"]["at"], "2026-11-19T03:00+08:00")
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

    def test_combined_brief_keeps_schedule_and_refreshes_confirmed_results(self):
        opens = time("2026-11-18T07:00+08:00")
        events = [{"date": "2026-11-18", "time": hour, "title": title, "cur": "USD", "impact": impact}
                  for hour, title, impact in [("08:30", "Retail sales", "high"), ("09:30", "Overview", "medium"),
                                               ("10:00", "Activity", "medium"), ("14:00", "Minutes", "medium")]]
        events[0].update(forecast="0.2%", fsrc="Survey", previous="0.8%", actual="0.3%", revised="0.7%",
                         metric="Headline sales", provenance={"url": "https://example.com/census"},
                         components=[{"label": "Headline sales", "actual": "0.3%"},
                                     {"label": "Control group", "actual": "0.2%", "previous": "0.1%"}])
        calendar = {"events": events, "through": "2026-11-30"}
        edition = build_edition(opens, opens, calendar, {}, {})
        self.assertEqual([row["title"] for row in edition["moreReleases"]], ["Minutes"])
        self.assertEqual(edition["upcoming"][0]["previous"], "0.8%")
        self.assertNotIn("actual", edition["upcoming"][0])
        self.assertNotIn("components", edition["upcoming"][0])
        self.assertNotIn("url", edition["upcoming"][0])
        self.assertEqual(edition["upcoming"][0]["forecastSource"], "Survey")
        report = {"id": "retail", "title": "Retail sales", "analysis": "Retail sales rose 0.3%.",
                  "url": "https://example.com/retail", "published": "2026-11-18T13:30:00+00:00"}
        refresh_edition(edition, time("2026-11-18T21:40+08:00"), calendar, {"items": [report, report]})
        self.assertEqual(edition["upcoming"][0]["actual"], "0.3%")
        self.assertEqual(edition["upcoming"][0]["revised"], "0.7%")
        self.assertEqual(edition["upcoming"][0]["components"], [{"label": "Control group", "actual": "0.2%", "previous": "0.1%"}])
        self.assertEqual(edition["upcoming"][0]["url"], "https://example.com/census")
        self.assertEqual(edition["focus"]["title"], "Overview")
        self.assertEqual(len(edition["updates"]), 1)
        self.assertEqual(edition["updates"][0]["published"], "2026-11-18T21:30:00+08:00")
        self.assertEqual(edition["generatedAt"], "2026-11-18T07:00:00+08:00")
        self.assertEqual(edition["refreshedAt"], "2026-11-18T21:40:00+08:00")

    def test_intraday_updates_keep_the_overnight_recap(self):
        opens = time("2026-11-18T07:00+08:00")
        def news_item(hour):
            return {"title": f"Update {hour}", "id": str(hour), "url": f"https://example.com/{hour}",
                    "published": f"2026-11-18T{hour:02}:00:00+08:00", "source": "Official feed", "context": "Release details."}
        edition = build_edition(opens, opens, {}, {"items": [news_item(hour) for hour in (2, 3, 4, 5)]}, {})
        refresh_edition(edition, time("2026-11-18T11:00+08:00"), {}, {"items": [news_item(hour) for hour in (8, 9, 10)]})
        self.assertEqual([item["id"] for item in edition["updates"]], ["10", "9", "5", "4", "3"])
        self.assertEqual(edition["updates"][-1]["source"], "Official feed")
        self.assertEqual(edition["updates"][-1]["context"], "Release details.")

    def test_outlook_requires_both_yields_from_the_expected_session(self):
        opens = time("2026-11-18T07:00+08:00")
        def markets(short, long, day="2026-11-17"):
            return {"tiles": {"y2": {"d1": short, "date": day}, "y10": {"d1": long, "date": day}}}
        self.assertEqual(market_outlook(opens, markets(-3, -5))["label"], "Bullish tilt")
        self.assertEqual(market_outlook(opens, markets(4, 3))["label"], "Bearish tilt")
        self.assertEqual(market_outlook(opens, markets(-3, 3))["label"], "Neutral")
        self.assertIn("10-year yield moved by less", market_outlook(opens, markets(-3, -2))["reason"])
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
        metrics = report_metrics(b"Issuer reported revenue for the third quarter of $12.3 billion, up 9% from a year ago. "
                                 b"GAAP and non-GAAP earnings per diluted share were $1.25 and $1.40, respectively. "
                                 b"The outlook for the fourth quarter is as follows: Revenue is expected to be $14 billion, plus or minus 2%.")
        self.assertEqual(metrics[0], {"label": "Revenue", "value": "$12.3 billion (up 9% year over year)"})
        summary = report_summary(metrics)
        self.assertEqual(summary, "Revenue $12.3 billion (up 9% year over year). GAAP diluted EPS $1.25. "
                                  "Next-quarter revenue guidance $14 billion \u00b12%.")


if __name__ == "__main__":
    unittest.main()
