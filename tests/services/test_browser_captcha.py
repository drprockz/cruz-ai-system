"""Tests for the captcha-detection heuristic."""
from pathlib import Path

import pytest

from services.browser import _detect_captcha

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("filename,expected_kind", [
    ("captcha_recaptcha.html", "recaptcha"),
    ("captcha_hcaptcha.html", "hcaptcha"),
    ("captcha_turnstile.html", "turnstile"),
])
def test_detect_real_captchas(filename, expected_kind):
    html = (FIXTURE_DIR / filename).read_text()
    kind = _detect_captcha(html, "https://example.com/page")
    assert kind == expected_kind


def test_text_heuristic_detects_human_check():
    html = "<html><body>please verify you are a human to continue</body></html>"
    assert _detect_captcha(html, "https://example.com") == "text_heuristic"


@pytest.mark.parametrize("filename", [
    "captcha_false_positive_docs.html",
    "captcha_false_positive_widget.html",
])
def test_no_false_positive_for_descriptive_pages(filename):
    html = (FIXTURE_DIR / filename).read_text()
    # The intent: descriptive content mentioning captcha should NOT be classified
    # as a captcha challenge. False positives are acceptable per spec, but these
    # specific cases should pass.
    assert _detect_captcha(html, "https://example.com") is None
