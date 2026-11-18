"""Dates worked out by rule: NYSE holidays and early closes, and releases that follow a fixed pattern."""
import datetime as dt


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(y, month, day)


def nth_weekday(y, m, weekday, n):
    """n-th weekday (Mon=0) of a month; n=-1 for the last."""
    if n > 0:
        d = dt.date(y, m, 1)
        d += dt.timedelta(days=(weekday - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)
    d = (dt.date(y, m + 1, 1) if m < 12 else dt.date(y + 1, 1, 1)) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def observed(d):
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


def nyse_holidays(y):
    """{date: name} of NYSE full closures in year y (standard NYSE rules)."""
    h = {}
    ny = dt.date(y, 1, 1)
    if ny.weekday() == 6:
        h[ny + dt.timedelta(days=1)] = "New Year's Day"
    elif ny.weekday() != 5:  # NYSE doesn't close the Friday before when Jan 1 is a Saturday
        h[ny] = "New Year's Day"
    h[nth_weekday(y, 1, 0, 3)] = "Martin Luther King Jr. Day"
    h[nth_weekday(y, 2, 0, 3)] = "Presidents' Day"
    h[easter(y) - dt.timedelta(days=2)] = "Good Friday"
    h[nth_weekday(y, 5, 0, -1)] = "Memorial Day"
    h[observed(dt.date(y, 6, 19))] = "Juneteenth"
    h[observed(dt.date(y, 7, 4))] = "Independence Day"
    h[nth_weekday(y, 9, 0, 1)] = "Labor Day"
    h[nth_weekday(y, 11, 3, 4)] = "Thanksgiving"
    h[observed(dt.date(y, 12, 25))] = "Christmas Day"
    return h


def nyse_early_closes(y):
    """{date: name} of 13:00 early closes."""
    e = {}
    thx = nth_weekday(y, 11, 3, 4)
    e[thx + dt.timedelta(days=1)] = "Day after Thanksgiving"
    xe = dt.date(y, 12, 24)
    if xe.weekday() < 5 and observed(dt.date(y, 12, 25)) != xe:
        e[xe] = "Christmas Eve"
    j3 = dt.date(y, 7, 3)
    if j3.weekday() < 5 and observed(dt.date(y, 7, 4)) != j3:
        e[j3] = "Day before Independence Day"
    return e


def business_days(y, m, holidays):
    d = dt.date(y, m, 1)
    out = []
    while d.month == m:
        if d.weekday() < 5 and d not in holidays:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def ism_dates(y, m, holidays):
    """ISM manufacturing: first business day of the month. Services: third business day."""
    b = business_days(y, m, holidays)
    return b[0], b[2]


def conference_board_date(y, m):
    """Consumer confidence: usually the last Tuesday of the month."""
    return nth_weekday(y, m, 1, -1)
