from __future__ import annotations

from typing import Any


def normalize_scan_value(value: Any) -> str:
    return str(value or "").strip()


def barcode_scan_candidates(value: Any) -> tuple[str, ...]:
    scanned = normalize_scan_value(value)
    if not scanned:
        return ()
    alternate = scanned[1:] if scanned.startswith("0") else f"0{scanned}"
    return tuple(dict.fromkeys(candidate for candidate in (scanned, alternate) if candidate))


def barcode_matches_scan(barcode: Any, scanned_value: Any) -> bool:
    normalized_barcode = normalize_scan_value(barcode).casefold()
    return bool(normalized_barcode) and normalized_barcode in {
        candidate.casefold() for candidate in barcode_scan_candidates(scanned_value)
    }


def sku_or_barcode_matches_scan(sku: Any, barcode: Any, scanned_value: Any) -> bool:
    scanned = normalize_scan_value(scanned_value)
    return bool(scanned) and (
        normalize_scan_value(sku).casefold() == scanned.casefold()
        or barcode_matches_scan(barcode, scanned)
    )
