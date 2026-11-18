import datetime as dt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from morning import SGT, build_edition, edition_time, publish
from engine import load


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
            publish(dt.datetime(2026, 11, 20, 8, tzinfo=SGT), data)
            publish(dt.datetime(2026, 11, 21, 6, 42, tzinfo=SGT), data)
            first = target.read_bytes()
            publish(dt.datetime(2026, 11, 21, 10, tzinfo=SGT), data)
            self.assertEqual(target.read_bytes(), first)
            self.assertEqual([item["date"] for item in load(target, {})["editions"]], ["2026-11-21", "2026-11-20"])


if __name__ == "__main__":
    unittest.main()
