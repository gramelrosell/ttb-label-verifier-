"""
Extractor abstraction.

A label-field Extractor takes raw image bytes and returns a dict of label
fields. We define an interface so the *source* of extraction is swappable
without touching the verification engine or UI.

Why this matters (per stakeholder Marcus Williams): federal networks frequently
block outbound traffic to cloud ML endpoints. The cloud-vision extractor gives
the best quality on real-world labels, but the local OCR extractor guarantees
the tool still functions fully offline / behind a restrictive firewall. Choosing
between them is a one-line config change.
"""

from abc import ABC, abstractmethod
from io import BytesIO

from PIL import Image, ImageOps, ImageFilter


# Fields every extractor attempts to populate. Missing -> empty string.
EXPECTED_FIELDS = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler_address",
    "country_of_origin",
    "government_warning",
]


class Extractor(ABC):
    """Reads label fields from image bytes."""

    name: str = "base"

    @abstractmethod
    def extract(self, image_bytes: bytes) -> dict:
        """Return a dict keyed by EXPECTED_FIELDS."""
        raise NotImplementedError

    @staticmethod
    def empty_result() -> dict:
        return {k: "" for k in EXPECTED_FIELDS}


def preprocess_image(image_bytes: bytes) -> bytes:
    """
    Clean up imperfect photos before OCR/vision (per Jenny Park: glare, bad
    angles, poor lighting). Conservative, lossless-ish enhancements:
      * auto-orient via EXIF
      * convert to grayscale and auto-contrast (helps glare/low light)
      * mild sharpening
    Returns PNG bytes. Used primarily to help the local OCR path; the vision
    path is robust enough that we pass the original but this is available.
    """
    img = Image.open(BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)            # fix phone-photo rotation
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray, cutoff=2)  # rescue under/over-exposure
    gray = gray.filter(ImageFilter.SHARPEN)
    out = BytesIO()
    gray.save(out, format="PNG")
    return out.getvalue()
