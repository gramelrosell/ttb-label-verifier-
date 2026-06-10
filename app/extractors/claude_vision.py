"""
Cloud-vision extractor (primary).

Uses Anthropic's Claude vision model to read a label image and return structured
fields in one call. A vision LLM dramatically outperforms classical OCR on real
labels: curved bottles, decorative fonts, glare, and odd angles (the exact pain
points raised by the compliance agents).

Requires ANTHROPIC_API_KEY in the environment. If the key is absent or the
network blocks the endpoint, the factory in __init__.py falls back to the local
extractor, so the app never hard-fails.
"""

import base64
import json
import os
from io import BytesIO

from PIL import Image

from .base import Extractor, EXPECTED_FIELDS


_PROMPT = """You are reading a U.S. alcohol beverage label for TTB compliance.
Extract these fields from the label image. Return ONLY a JSON object, no prose,
no markdown fences. Use an empty string for any field you cannot find.

Fields:
- brand_name
- class_type            (e.g. "Kentucky Straight Bourbon Whiskey")
- alcohol_content       (verbatim, e.g. "45% Alc./Vol. (90 Proof)")
- net_contents          (e.g. "750 mL")
- bottler_address       (name and address of bottler/producer)
- country_of_origin
- government_warning    (transcribe the FULL warning EXACTLY as printed,
                         preserving the original capitalization of the
                         "GOVERNMENT WARNING:" prefix — this casing matters)

Return exactly: {"brand_name":"","class_type":"","alcohol_content":"",
"net_contents":"","bottler_address":"","country_of_origin":"",
"government_warning":""}"""


class ClaudeVisionExtractor(Extractor):
    name = "claude-vision"

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        # Imported lazily so the local-only deployment doesn't need the package.
        from anthropic import Anthropic

        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model

    def _to_jpeg_b64(self, image_bytes: bytes) -> str:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        # Downscale large photos to keep latency under the 5s budget.
        img.thumbnail((1568, 1568))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return base64.standard_b64encode(buf.getvalue()).decode()

    def extract(self, image_bytes: bytes) -> dict:
        b64 = self._to_jpeg_b64(image_bytes)
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64,
                    }},
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        result = self.empty_result()
        try:
            parsed = json.loads(text)
            for k in EXPECTED_FIELDS:
                if k in parsed and parsed[k]:
                    result[k] = str(parsed[k]).strip()
        except json.JSONDecodeError:
            pass  # leave fields empty; verifier will flag missing data
        return result
