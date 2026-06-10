"""
Extractor factory.

Selects the best available extractor at runtime:
  1. If EXTRACTOR=tesseract is set, or no API key is present -> local OCR.
  2. Otherwise -> Claude vision (primary).

This is the single place where the cloud/offline tradeoff is decided, so a
firewalled federal deployment only changes one environment variable.
"""

import os

from .base import Extractor


def get_extractor() -> Extractor:
    choice = os.environ.get("EXTRACTOR", "auto").lower()

    if choice == "tesseract":
        from .tesseract_ocr import TesseractExtractor
        return TesseractExtractor()

    if choice in ("claude", "auto") and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from .claude_vision import ClaudeVisionExtractor
            return ClaudeVisionExtractor()
        except Exception:
            pass  # fall through to local

    # Default / fallback: works with no network.
    from .tesseract_ocr import TesseractExtractor
    return TesseractExtractor()


__all__ = ["get_extractor", "Extractor"]
