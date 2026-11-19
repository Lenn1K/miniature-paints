"""EAN-Hilfen: Prüfziffer, Normalisierung, Herleitung aus Herstellercodes."""
from __future__ import annotations

import re

VALLEJO_PREFIX = "8429551"


def check_digit(body: str) -> int:
    """Prüfziffer für EAN-8/EAN-13 (body ohne Prüfziffer)."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def is_valid_ean(code: str | None) -> bool:
    return bool(code) and bool(re.fullmatch(r"\d{8}|\d{13}", code)) and check_digit(code[:-1]) == int(code[-1])


def normalize_ean(code: str | None) -> str | None:
    """Ziffern übernehmen, UPC-A (12) -> EAN-13; ungültig -> None."""
    if not code:
        return None
    digits = re.sub(r"\D", "", str(code))
    if len(digits) == 12:
        digits = "0" + digits
    return digits if is_valid_ean(digits) else None


def vallejo_ean(code: str | None) -> str | None:
    """'74.265' -> '8429551742658'. Nur für Codes der Form NN.NNN."""
    m = re.fullmatch(r"(\d{2})\.?(\d{3})", (code or "").strip())
    if not m:
        return None
    body = VALLEJO_PREFIX + m[1] + m[2]
    return body + str(check_digit(body))


def gsw_ean(reference: str | None) -> str | None:
    """Green Stuff World: Referenz '<EAN>ES' -> EAN."""
    m = re.fullmatch(r"(\d{13})ES", (reference or "").strip().upper())
    return normalize_ean(m[1]) if m else None
