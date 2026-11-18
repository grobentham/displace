"""Record source checks independently of the data validation score."""

MONITORED_SOURCES = (
    "fred", "alfred", "bls", "bea", "census", "treasury", "nyFed", "nasdaqCalendar",
)
CHECKS = {}


def record(source, ok):
    CHECKS.setdefault(source, []).append(bool(ok))


def snapshot(previous, checked_at):
    result = {}
    for source in MONITORED_SOURCES:
        prior = previous.get(source, {})
        checks = CHECKS.get(source, [])
        successes = sum(checks)
        if not checks:
            state = "not_checked"
        elif not successes:
            state = "unavailable"
        elif successes < len(checks):
            state = "partial"
        else:
            state = "available"
        result[source] = {
            "state": state,
            "checkedAt": checked_at if checks else prior.get("checkedAt"),
            "lastSuccessAt": checked_at if successes else prior.get("lastSuccessAt"),
        }
    return result
