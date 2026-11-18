"""Backup trigger for the engine, for when GitHub's own cron schedule doesn't fire.

Run by .github/workflows/scheduler.yml. It works out the next engine slot (the same times as the cron lines in
engine.yml), waits for it, starts the Engine workflow unless one already ran in the last 20 minutes, then starts
a fresh copy of itself to wait for the slot after that. GitHub allows a workflow to start workflows with its own
built-in token (workflow_dispatch), so no keys are involved. A job can wait at most a few hours, so long gaps are
bridged by restarting itself without starting the engine.
"""
import datetime as dt
import re
import sys

MAX_WAIT = dt.timedelta(hours=5, minutes=30)


def slots(workflow_text):
    """[(minute, hour, day-of-week set)] from the cron lines of engine.yml (UTC)."""
    out = []
    for m, h, dow in re.findall(r'cron:\s*"(\d+) (\d+) \* \* ([\d*,-]+)"', workflow_text):
        if dow == "*":
            days = set(range(7))
        else:
            days = set()
            for part in dow.split(","):
                a, _, b = part.partition("-")
                days |= set(range(int(a), int(b or a) + 1))
        out.append((int(m), int(h), {d % 7 for d in days}))  # cron: 0 = Sunday
    return out


def next_slot(now, workflow_text):
    best = None
    for m, h, days in slots(workflow_text):
        for add in range(8):
            day = (now + dt.timedelta(days=add)).date()
            t = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=dt.timezone.utc)
            cron_dow = (t.weekday() + 1) % 7  # Python Monday=0 -> cron Monday=1
            if t > now and cron_dow in days:
                best = t if best is None or t < best else best
                break
    return best


def main():
    now = dt.datetime.now(dt.timezone.utc)
    text = open(sys.argv[1]).read()
    nxt = next_slot(now, text)
    wait = nxt - now
    fire = wait <= MAX_WAIT
    print(f"next={nxt.isoformat()} wait={int(min(wait, MAX_WAIT).total_seconds())} fire={'yes' if fire else 'no'}")


if __name__ == "__main__":
    main()
