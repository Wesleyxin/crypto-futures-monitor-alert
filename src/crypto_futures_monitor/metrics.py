from __future__ import annotations


def baseline_value(vols: list[float], method: str) -> float:
    if not vols:
        return 1e-12
    if method == "median":
        s = sorted(vols)
        n = len(s)
        m = n // 2
        return float(s[m]) if n % 2 else (float(s[m - 1]) + float(s[m])) / 2.0
    return float(sum(vols)) / float(len(vols))
