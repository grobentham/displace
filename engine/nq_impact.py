"""Export an NQ event study as a snapshot for the calendar's News Impact card."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
from statistics import median, quantiles


RELEASE_TYPES = ("cpi", "payrolls")
MINUTES = 15


def number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError("Expected a finite return in basis points")
    return value


def snapshot(study):
    output = {"version": 1, "minutes": MINUTES, "summaries": {}, "observations": {}}
    for kind in RELEASE_TYPES:
        moves, controls, timestamps = [], [], []
        for event in study["events"]:
            if event["event"] != kind:
                continue
            when = datetime.strptime(event["time_et"], "%Y-%m-%d %H:%M").isoformat(timespec="minutes")
            key = f"{kind}:{when}"
            if key in output["observations"]:
                raise ValueError(f"Repeated release in NQ event study: {key}")
            move = number(event["move_bps"])
            moves.append(abs(move))
            timestamps.append(when)
            output["observations"][key] = round(move, 4)
            if event["control_bps"] is not None:
                control = number(event["control_bps"])
                if control < 0:
                    raise ValueError(f"Negative absolute comparison move: {key}")
                controls.append(control)
        if len(moves) < 2:
            continue
        q1, _, q3 = quantiles(moves, n=4, method="inclusive")
        output["summaries"][kind] = {
            "count": len(moves),
            "medianBps": round(median(moves), 4),
            "lowerBps": round(q1, 4),
            "upperBps": round(q3, 4),
            "controlBps": round(median(controls), 4) if controls else None,
            "through": max(timestamps)[:10],
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = snapshot(json.loads(args.study.read_text(encoding="utf-8")))
    if not data["summaries"]:
        raise SystemExit("The study needs at least two completed windows for a release type.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {len(data['observations'])} release observations.")


if __name__ == "__main__":
    main()
