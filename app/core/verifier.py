"""
Verification engine.

Compares the fields extracted from a label image against the data submitted in
the application, and produces a structured, per-field result. This is the heart
of the tool — it encodes the judgment that a human agent applies:

  * Brand name, type, ABV, net contents -> fuzzy match (tolerant of casing,
    punctuation, and minor OCR noise). Dave Morrison's "STONE'S THROW" vs
    "Stone's Throw" case must pass.
  * ABV -> additionally normalized so "45% Alc./Vol. (90 Proof)" and "45%"
    compare on the underlying number.
  * Government warning -> exact statutory text + a separate check that the
    "GOVERNMENT WARNING:" prefix is uppercase.
"""

import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from enum import Enum
from typing import Optional

from .requirements import (
    FIELD_SPECS,
    FieldSpec,
    MatchMode,
    GOVERNMENT_WARNING_TEXT,
    GOVERNMENT_WARNING_PREFIX,
)


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"   # present but worth a human glance
    MISSING = "missing"   # required field not found on the label


@dataclass
class FieldResult:
    key: str
    display_name: str
    status: Status
    application_value: Optional[str]
    label_value: Optional[str]
    similarity: Optional[float]
    message: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class VerificationReport:
    overall_pass: bool
    results: list[FieldResult]
    summary: str

    def to_dict(self) -> dict:
        return {
            "overall_pass": self.overall_pass,
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results],
        }


# --- normalization helpers -------------------------------------------------

def _normalize(text: Optional[str]) -> str:
    """Lowercase, strip punctuation, collapse whitespace. For fuzzy compares."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^\w\s%./]", " ", text)   # keep % . / for ABV/contents
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


_ABV_RE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%")


def _extract_abv(text: Optional[str]) -> Optional[float]:
    """Pull the percentage number out of an ABV string."""
    if not text:
        return None
    m = _ABV_RE.search(text)
    return float(m.group(1)) if m else None


def _normalize_warning(text: Optional[str]) -> str:
    """Normalize warning text for verbatim comparison: collapse whitespace,
    unify casing of everything EXCEPT we check the prefix casing separately."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


# --- per-field matchers ----------------------------------------------------

def _match_fuzzy(spec: FieldSpec, app_val: str, label_val: str) -> FieldResult:
    # Special numeric handling for ABV.
    if spec.key == "alcohol_content":
        app_abv = _extract_abv(app_val)
        label_abv = _extract_abv(label_val)
        if app_abv is not None and label_abv is not None:
            if abs(app_abv - label_abv) < 0.05:
                return FieldResult(spec.key, spec.display_name, Status.PASS,
                                   app_val, label_val, 1.0,
                                   f"ABV matches ({label_abv}%).")
            return FieldResult(spec.key, spec.display_name, Status.FAIL,
                               app_val, label_val, 0.0,
                               f"ABV mismatch: application {app_abv}% vs "
                               f"label {label_abv}%.")

    sim = _similarity(_normalize(app_val), _normalize(label_val))
    if sim >= spec.fuzzy_threshold:
        msg = "Matches."
        if _normalize(app_val) != _normalize(label_val):
            msg = "Matches (minor formatting/casing difference, accepted)."
        return FieldResult(spec.key, spec.display_name, Status.PASS,
                           app_val, label_val, round(sim, 3), msg)
    return FieldResult(spec.key, spec.display_name, Status.FAIL,
                       app_val, label_val, round(sim, 3),
                       f"Mismatch (similarity {sim:.0%}, "
                       f"threshold {spec.fuzzy_threshold:.0%}).")


def _match_presence(spec: FieldSpec, app_val: str, label_val: str) -> FieldResult:
    if label_val and label_val.strip():
        return FieldResult(spec.key, spec.display_name, Status.PASS,
                           app_val, label_val, None, "Present on label.")
    status = Status.MISSING if spec.required else Status.WARNING
    msg = ("Required field not detected on label." if spec.required
           else "Not detected (may be optional for this product).")
    return FieldResult(spec.key, spec.display_name, status,
                       app_val, label_val, None, msg)


def _match_government_warning(spec: FieldSpec, label_val: str) -> FieldResult:
    """The strict one. The warning is compared against the statutory text, and
    the 'GOVERNMENT WARNING:' prefix must be uppercase."""
    if not label_val or not label_val.strip():
        return FieldResult(spec.key, spec.display_name, Status.MISSING,
                           GOVERNMENT_WARNING_TEXT, label_val, 0.0,
                           "Government warning not detected on label. "
                           "This is mandatory on all alcohol beverages.")

    raw = label_val.strip()

    # 1. Casing check on the prefix (Jenny Park: title-case is a rejection).
    prefix_ok = GOVERNMENT_WARNING_PREFIX in raw  # exact uppercase substring
    has_titlecase = re.search(r"government warning\s*:", raw, re.IGNORECASE) \
        and not prefix_ok

    # 2. Verbatim text comparison (case-insensitive on body, whitespace-normal).
    sim = _similarity(_normalize_warning(label_val).lower(),
                      _normalize_warning(GOVERNMENT_WARNING_TEXT).lower())

    if not prefix_ok and has_titlecase:
        return FieldResult(spec.key, spec.display_name, Status.FAIL,
                           GOVERNMENT_WARNING_TEXT, label_val, round(sim, 3),
                           "REJECT: 'GOVERNMENT WARNING:' must be in uppercase. "
                           "Found incorrect casing (e.g. title case).")

    if not prefix_ok:
        return FieldResult(spec.key, spec.display_name, Status.FAIL,
                           GOVERNMENT_WARNING_TEXT, label_val, round(sim, 3),
                           "REJECT: required 'GOVERNMENT WARNING:' prefix "
                           "(uppercase) not found.")

    if sim >= spec.fuzzy_threshold:
        return FieldResult(spec.key, spec.display_name, Status.PASS,
                           GOVERNMENT_WARNING_TEXT, label_val, round(sim, 3),
                           "Government warning present and matches statutory "
                           "text.")

    return FieldResult(spec.key, spec.display_name, Status.FAIL,
                       GOVERNMENT_WARNING_TEXT, label_val, round(sim, 3),
                       f"Warning text deviates from statutory wording "
                       f"(match {sim:.0%}). Wording must be verbatim.")


# --- public API ------------------------------------------------------------

def verify(application: dict, extracted: dict) -> VerificationReport:
    """
    application: the values submitted in the COLA application.
    extracted:   the fields read off the label image by an Extractor.
    """
    results: list[FieldResult] = []

    for spec in FIELD_SPECS:
        app_val = (application.get(spec.key) or "").strip()
        label_val = (extracted.get(spec.key) or "").strip()

        if spec.key == "government_warning":
            results.append(_match_government_warning(spec, label_val))
            continue

        # If neither side has a value and it's optional, skip cleanly.
        if not app_val and not label_val and not spec.required:
            results.append(FieldResult(spec.key, spec.display_name, Status.PASS,
                                       app_val, label_val, None,
                                       "Not applicable / not provided."))
            continue

        if spec.match_mode == MatchMode.FUZZY:
            if not app_val:
                results.append(_match_presence(spec, app_val, label_val))
            else:
                results.append(_match_fuzzy(spec, app_val, label_val))
        elif spec.match_mode == MatchMode.PRESENCE:
            results.append(_match_presence(spec, app_val, label_val))

    overall = all(r.status == Status.PASS for r in results)
    n_fail = sum(1 for r in results if r.status in (Status.FAIL, Status.MISSING))
    if overall:
        summary = "PASS — all checked fields match the application."
    else:
        summary = f"REVIEW NEEDED — {n_fail} field(s) require attention."

    return VerificationReport(overall, results, summary)
