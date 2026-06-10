"""
TTB label field requirements and reference constants.

The Government Warning text below is the statutory wording mandated by the
Alcoholic Beverage Labeling Act of 1988 (27 CFR 16.21). It must appear on the
label verbatim. Per stakeholder feedback (Jenny Park), the literal string
"GOVERNMENT WARNING:" must be uppercase and bold; the rest must match
word-for-word. We verify the text exactly and surface the casing/bold rule as a
separate, explicit check.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# The exact statutory Government Warning. Source: 27 CFR 16.21.
GOVERNMENT_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability to "
    "drive a car or operate machinery, and may cause health problems."
)

# The prefix that must be uppercase (and bold on the physical label).
GOVERNMENT_WARNING_PREFIX = "GOVERNMENT WARNING:"


class MatchMode(str, Enum):
    """How strictly a field's value is compared against the application."""

    FUZZY = "fuzzy"          # case/punctuation-insensitive, tolerant of OCR noise
    EXACT = "exact"          # must match word-for-word after light normalization
    PRESENCE = "presence"    # only needs to be present and non-empty


@dataclass
class FieldSpec:
    """Defines one verifiable label field."""

    key: str
    display_name: str
    match_mode: MatchMode
    required: bool = True
    # Minimum similarity (0-1) to count as a fuzzy match.
    fuzzy_threshold: float = 0.85
    notes: Optional[str] = None


# The set of fields a TTB agent checks. Brand/type/ABV/etc. use judgment-friendly
# fuzzy matching (per Dave Morrison: "STONE'S THROW" == "Stone's Throw"). The
# government warning is handled specially (exact text + casing rule).
FIELD_SPECS: list[FieldSpec] = [
    FieldSpec("brand_name", "Brand Name", MatchMode.FUZZY,
              notes="Case/punctuation-insensitive per agent guidance."),
    FieldSpec("class_type", "Class / Type Designation", MatchMode.FUZZY),
    FieldSpec("alcohol_content", "Alcohol Content (ABV)", MatchMode.FUZZY,
              notes="Normalized to compare the numeric percentage."),
    FieldSpec("net_contents", "Net Contents", MatchMode.FUZZY),
    FieldSpec("bottler_address", "Name & Address of Bottler/Producer",
              MatchMode.PRESENCE, required=False),
    FieldSpec("country_of_origin", "Country of Origin",
              MatchMode.PRESENCE, required=False,
              notes="Required only for imports."),
    FieldSpec("government_warning", "Government Health Warning",
              MatchMode.EXACT, fuzzy_threshold=0.97,
              notes="Statutory text. Must be verbatim; prefix must be UPPERCASE."),
]
