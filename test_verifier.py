"""
Tests for the verification engine. These encode the specific judgment calls
raised by the compliance agents in the discovery interviews.
"""

from app.core.verifier import verify, Status
from app.core.requirements import GOVERNMENT_WARNING_TEXT


def _field(report, key):
    return next(r for r in report.results if r.key == key)


def test_dave_stones_throw_casing_passes():
    """Dave Morrison: 'STONE'S THROW' on label vs 'Stone's Throw' in app must
    be accepted — same brand, just casing."""
    app = {"brand_name": "Stone's Throw"}
    extracted = {"brand_name": "STONE'S THROW",
                 "government_warning": GOVERNMENT_WARNING_TEXT}
    r = verify(app, extracted)
    assert _field(r, "brand_name").status == Status.PASS


def test_abv_normalizes_proof_suffix():
    """'45% Alc./Vol. (90 Proof)' must match an application value of '45%'."""
    app = {"alcohol_content": "45%"}
    extracted = {"alcohol_content": "45% Alc./Vol. (90 Proof)",
                 "government_warning": GOVERNMENT_WARNING_TEXT}
    r = verify(app, extracted)
    assert _field(r, "alcohol_content").status == Status.PASS


def test_abv_mismatch_fails():
    app = {"alcohol_content": "40%"}
    extracted = {"alcohol_content": "45% Alc./Vol.",
                 "government_warning": GOVERNMENT_WARNING_TEXT}
    r = verify(app, extracted)
    assert _field(r, "alcohol_content").status == Status.FAIL


def test_jenny_titlecase_warning_rejected():
    """Jenny Park: 'Government Warning' in title case must be rejected; the
    prefix must be uppercase."""
    bad = GOVERNMENT_WARNING_TEXT.replace("GOVERNMENT WARNING:",
                                          "Government Warning:")
    r = verify({}, {"government_warning": bad})
    gw = _field(r, "government_warning")
    assert gw.status == Status.FAIL
    assert "uppercase" in gw.message.lower()


def test_correct_warning_passes():
    r = verify({}, {"government_warning": GOVERNMENT_WARNING_TEXT})
    assert _field(r, "government_warning").status == Status.PASS


def test_missing_warning_flagged():
    r = verify({}, {"government_warning": ""})
    assert _field(r, "government_warning").status == Status.MISSING


def test_altered_warning_wording_fails():
    """Creative rewording of the statutory text must fail."""
    altered = ("GOVERNMENT WARNING: Drinking is bad for you and you should not "
               "drive afterwards.")
    r = verify({}, {"government_warning": altered})
    assert _field(r, "government_warning").status == Status.FAIL


def test_overall_pass_when_all_match():
    app = {"brand_name": "OLD TOM DISTILLERY",
           "class_type": "Kentucky Straight Bourbon Whiskey",
           "alcohol_content": "45% Alc./Vol.", "net_contents": "750 mL"}
    extracted = dict(app, government_warning=GOVERNMENT_WARNING_TEXT)
    r = verify(app, extracted)
    assert r.overall_pass is True
