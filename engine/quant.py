"""Small, tested building blocks for the daily bias: logistic and OLS fits, walk-forward testing, scoring.

Everything is judged out of sample: a model is refit each year on the years before it and scored on that year.
"""
import math
from statistics import NormalDist

import numpy as np


def sig(x):
    return 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def logit_fit(X, y, lam=2.0, iters=30):
    """Ridge logistic regression with an intercept (the intercept is not penalised). X: (n, k)."""
    n, k = X.shape
    A = np.c_[np.ones(n), X]
    pen = np.r_[0.0, np.full(k, lam)]
    b = np.zeros(k + 1)
    for _ in range(iters):
        p = sig(A @ b)
        g = A.T @ (p - y) + pen * b
        H = (A * (p * (1 - p))[:, None]).T @ A + np.diag(pen)
        step = np.linalg.solve(H, g)
        b -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return b


def standardize(Xtr, *others):
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd == 0] = 1.0
    return [(Xtr - mu) / sd] + [(o - mu) / sd for o in others], (mu, sd)


def walk_forward_logit(years, X, y, first=2006, min_train=500):
    """Refit each year on the years before it. Returns arrays (year, p, p0, y) for the scored days."""
    out = []
    for yr in np.unique(years):
        if yr < first:
            continue
        tr, te = years < yr, years == yr
        if tr.sum() < min_train or not te.any():
            continue
        (Xt, Xe), _ = standardize(X[tr], X[te])
        b = logit_fit(Xt, y[tr])
        p = sig(np.c_[np.ones(te.sum()), Xe] @ b)
        out.append(np.c_[np.full(te.sum(), yr), p, np.full(te.sum(), y[tr].mean()), y[te]])
    return np.vstack(out) if out else np.zeros((0, 4))


def brier_skill(w):
    if len(w) == 0:
        return None
    b0 = np.sum((w[:, 2] - w[:, 3]) ** 2)
    return float(1 - np.sum((w[:, 1] - w[:, 3]) ** 2) / b0) if b0 else None


def t_needed(k, alpha=0.05):
    """One-sided z for alpha split across k tests (Bonferroni)."""
    return NormalDist().inv_cdf(1 - alpha / max(1, k))


def judge(w, t_req):
    """Out-of-sample Brier skill over the base rate with a Diebold-Mariano t on the score differences;
    passing needs t >= t_req and positive skill in both halves and in the last three years."""
    if len(w) < 400:
        return {"skill": None, "tested": False}
    half = len(w) // 2
    last = w[:, 0].max()
    s, s1, s2 = brier_skill(w), brier_skill(w[:half]), brier_skill(w[half:])
    s3 = brier_skill(w[w[:, 0] >= last - 2])
    d = (w[:, 2] - w[:, 3]) ** 2 - (w[:, 1] - w[:, 3]) ** 2
    t = float(d.mean() / (d.std() / math.sqrt(len(d)))) if d.std() > 0 else 0.0
    ok = t >= t_req and all(x is not None and x > 0 for x in (s1, s2, s3))
    r = lambda x: round(x, 4) if x is not None else None
    return {"skill": r(s), "t": round(t, 2), "halves": [r(s1), r(s2)], "recent": r(s3), "tested": bool(ok)}


def reliability(p, y, bins=10, min_n=25):
    """[[mean forecast, observed frequency, n], ...] over equal-width probability bins."""
    out = []
    edges = np.linspace(0, 1, bins + 1)
    for a, b in zip(edges[:-1], edges[1:]):
        m = (p >= a) & (p < b if b < 1 else p <= b)
        if m.sum() >= min_n:
            out.append([round(float(p[m].mean()), 3), round(float(y[m].mean()), 3), int(m.sum())])
    return out


def ols(A, y):
    return np.linalg.lstsq(A, y, rcond=None)[0]


def har_walk_forward(years, F, y, base, first, train_from):
    """Walk-forward OLS on log range. base: the old forecast (log of the 20-day average range) for comparison.
    Returns dict of out-of-sample arrays: pred, lo, hi (80% band), y, base, oldlo, oldhi, year, idx."""
    rows = {k: [] for k in ("idx", "pred", "lo", "hi", "y", "base", "oldlo", "oldhi", "c")}
    ok = ~np.isnan(F).any(1) & ~np.isnan(y) & ~np.isnan(base)
    for yr in np.unique(years):
        if yr < first:
            continue
        tr = ok & (years < yr) & (years >= train_from)
        te = ok & (years == yr)
        if tr.sum() < 300 or not te.any():
            continue
        A = np.c_[np.ones(tr.sum()), F[tr]]
        b = ols(A, y[tr])
        res = y[tr] - A @ b
        q10, q90 = np.quantile(res, [0.1, 0.9])
        ro = y[tr] - base[tr]
        o10, o50, o90 = np.quantile(ro, [0.1, 0.5, 0.9])
        pe = np.c_[np.ones(te.sum()), F[te]] @ b
        idx = np.where(te)[0]
        rows["idx"] += list(idx)
        rows["pred"] += list(pe)
        rows["lo"] += list(pe + q10)
        rows["hi"] += list(pe + q90)
        rows["y"] += list(y[te])
        rows["base"] += list(base[te] + o50)
        rows["oldlo"] += list(base[te] + o10)
        rows["oldhi"] += list(base[te] + o90)
    return {k: np.array(v) for k, v in rows.items()}


def har_fit(F, y, mask):
    A = np.c_[np.ones(mask.sum()), F[mask]]
    b = ols(A, y[mask])
    res = y[mask] - A @ b
    return b, np.quantile(res, [0.1, 0.5, 0.9])
