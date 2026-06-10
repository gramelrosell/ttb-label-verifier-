# 🏛️ AI-Powered Alcohol Label Verification

A prototype that compares an alcohol-beverage **label image** against the data
in its **COLA application** and flags any mismatches — the routine
"does-the-label-match-the-form" check that TTB compliance agents perform
thousands of times a week.

**Author:** Gramel Rosell Jr.

---

## What it does

Upload a label photo, enter the application fields, and the app:

1. **Reads the label** with a vision/OCR engine (brand, class/type, ABV, net
   contents, bottler, country of origin, government warning).
2. **Verifies each field** against the application using rules that mirror an
   agent's judgment.
3. **Returns a clear PASS / NEEDS REVIEW** result in a few seconds, with a
   per-field breakdown.

It also supports **batch upload** (hundreds of labels at once) with a
downloadable CSV of results.

---

## How the design responds to the discovery interviews

Every major decision traces back to something a stakeholder said:

| Stakeholder | Need | How it's addressed |
|---|---|---|
| **Sarah Chen** | "If we can't get results back in ~5 seconds, nobody uses it." | Every run is timed and shown; images are downscaled before the vision call to stay within budget. |
| **Sarah Chen** | "Something my 73-year-old mother could figure out." Half the team is 50+. | Large fonts, high contrast, one obvious button, plain PASS / NEEDS REVIEW banners, no jargon. |
| **Sarah / Janet** | Importers dump 200–300 labels at once. | Dedicated **Batch upload** tab with progress bar and CSV export. |
| **Marcus Williams** | Federal firewalls block outbound ML endpoints. | Extraction sits behind a swappable `Extractor` interface. Cloud vision is primary; **local Tesseract OCR is a one-variable fallback** that needs no network. |
| **Marcus Williams** | "Don't store anything sensitive." | Images are processed in memory and never written to disk. |
| **Dave Morrison** | "STONE'S THROW" vs "Stone's Throw" is obviously the same. | Brand/type/etc. use **fuzzy matching** (case/punctuation-insensitive). |
| **Jenny Park** | The warning must be verbatim; "Government Warning" in title case = rejection. | The government warning gets a **strict check**: statutory text match **plus** an uppercase-prefix rule. |
| **Jenny Park** | Photos have glare, bad angles, poor lighting. | Image preprocessing (EXIF auto-orient, autocontrast, sharpen) before OCR; the vision model handles imperfect images natively. |

---

## Architecture

```
streamlit_app.py         ← agent-facing UI (single + batch)
app/
  api.py                 ← optional FastAPI backend (/verify, /verify-batch)
  core/
    requirements.py      ← TTB field specs + statutory warning text
    verifier.py          ← the verification engine (fuzzy + strict matching)
  extractors/
    base.py              ← Extractor interface + image preprocessing
    claude_vision.py     ← primary reader (Anthropic Claude vision)
    tesseract_ocr.py     ← offline fallback reader (no network)
    __init__.py          ← factory: picks the best available reader
tests/test_verifier.py   ← unit tests for every stakeholder edge case
samples/                 ← generator + example compliant / non-compliant labels
```

The **Extractor interface** is the core architectural idea: the verification
engine and UI don't know or care whether a field came from a cloud model or
local OCR, so a firewalled deployment switches readers with one environment
variable.

---

## Quick start

```bash
git clone <your-repo-url>
cd ttb-label-verifier
pip install -r requirements.txt

# (offline OCR path also needs the tesseract binary)
#   macOS:   brew install tesseract
#   Ubuntu:  sudo apt-get install tesseract-ocr

streamlit run streamlit_app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

### Choosing the reader

- **Best quality (recommended):** set an API key and the app uses Claude vision.
  ```bash
  export ANTHROPIC_API_KEY=sk-ant-...
  ```
- **Fully offline / firewalled:** leave the key unset, or force local OCR:
  ```bash
  export EXTRACTOR=tesseract
  ```

The app runs out-of-the-box with **no API key** using local OCR.

### Generate test labels

```bash
PYTHONPATH=. python samples/generate_samples.py
# creates a compliant label and a non-compliant (title-case warning) one
```

### Run the tests

```bash
PYTHONPATH=. python -m pytest tests/ -q
```

### (Optional) Run the API backend

```bash
uvicorn app.api:app --reload
# POST /verify (one label) and POST /verify-batch (many)
```

---

## Deployment

Deployed on **Streamlit Community Cloud** (single-process, free, GitHub-linked):

1. Push this repo to GitHub.
2. At share.streamlit.io, create an app pointing at `streamlit_app.py`.
3. (Optional) add `ANTHROPIC_API_KEY` under **Settings → Secrets** to enable the
   vision reader; otherwise it runs on local OCR.

`packages.txt` installs the Tesseract system binary automatically.

**Live URL:** _<paste your deployed URL here once published>_

---

## Assumptions & trade-offs

- **Standalone prototype**, not integrated with COLA — matches Marcus's guidance
  that integration is "years away."
- **The application data is entered manually** (or passed as JSON in batch mode).
  A production version would pull it directly from the COLA record.
- The **statutory warning text** is hard-coded from 27 CFR 16.21. Beer/wine have
  some specific-wording allowances not fully enumerated here.
- **Fuzzy thresholds** (default 85%) are tuned for the sample labels; production
  would calibrate these against a real labeled dataset.
- The **local OCR path is the floor, not the ceiling** — Tesseract struggles
  with stylized fonts and curved bottles, which is exactly why cloud vision is
  the primary reader. The interface lets you upgrade to an on-prem vision model
  later without touching the rest of the code.
- Nothing is persisted; there is no auth. Both are deliberate for a prototype
  and called out as required before any production deployment.

---

## What I'd build next with more time

- Pull application data straight from a COLA export so agents type nothing.
- A confidence score per field and a "needs human look" queue.
- An on-prem vision model option for firewalled networks (drop-in `Extractor`).
- Field bounding-box overlays so agents see *where* on the label each value was
  read from.
