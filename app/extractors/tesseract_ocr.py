"""
Local OCR extractor (offline fallback).

Uses Tesseract (via pytesseract) to read text off the label with no network
access. Classical OCR is far less robust than a vision model on stylized labels,
so we apply preprocessing and use heuristics/regex to pull fields out of the
raw text. This path guarantees the tool works behind a firewall that blocks
cloud ML endpoints.

Requires the `tesseract-ocr` system package and `pytesseract`.
"""

import re

from .base import Extractor, preprocess_image


class TesseractExtractor(Extractor):
    name = "tesseract-ocr"

    def __init__(self):
        import pytesseract  # lazy import
        from PIL import Image
        self._pytesseract = pytesseract
        self._Image = Image

    def _ocr(self, image_bytes: bytes) -> str:
        from io import BytesIO
        clean = preprocess_image(image_bytes)
        img = self._Image.open(BytesIO(clean))
        return self._pytesseract.image_to_string(img)

    def extract(self, image_bytes: bytes) -> dict:
        text = self._ocr(image_bytes)
        result = self.empty_result()
        result["_raw_ocr_text"] = text  # surfaced in UI for transparency

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # ABV: first "NN% ... " pattern.
        m = re.search(r"\d{1,2}(?:\.\d+)?\s*%\s*(?:alc|abv|alcohol)?[^\n]*",
                      text, re.IGNORECASE)
        if m:
            result["alcohol_content"] = m.group(0).strip()

        # Net contents: ml / l / fl oz patterns.
        m = re.search(r"\d+(?:\.\d+)?\s*(?:ml|mL|L|fl\.?\s*oz)", text)
        if m:
            result["net_contents"] = m.group(0).strip()

        # Government warning: capture from the prefix to the end of the block.
        m = re.search(r"government\s+warning\s*:.*", text,
                      re.IGNORECASE | re.DOTALL)
        if m:
            result["government_warning"] = re.sub(r"\s+", " ", m.group(0)).strip()

        # Country of origin.
        m = re.search(r"product\s+of\s+([A-Za-z ]+)", text, re.IGNORECASE)
        if m:
            result["country_of_origin"] = m.group(0).strip()

        # Brand name heuristic: first prominent line that isn't a known field.
        for ln in lines:
            low = ln.lower()
            if any(t in low for t in ("warning", "alc", "%", "ml", "vol",
                                      "proof", "contents")):
                continue
            if len(ln) >= 3:
                result["brand_name"] = ln
                break

        return result
