"""
Streamlit UI — the agent-facing application.

Design priorities come straight from the discovery interviews:
  * "Something my 73-year-old mother could figure out." Big controls, plain
    language, no hunting for buttons, clear PASS / NEEDS REVIEW outcomes.
  * Half the team is over 50 -> large text, high contrast, minimal chrome.
  * Results in ~5 seconds -> we time every run and show it.
  * Batch mode for peak-season importers (200-300 labels at once).

This calls the verification engine directly (no separate API server needed for
the deployed Streamlit app), which keeps the single-process deployment simple.
"""

import io
import time
import pandas as pd
import streamlit as st

from app.extractors import get_extractor
from app.core.verifier import verify, Status

st.set_page_config(page_title="TTB Label Verifier", page_icon="🏛️",
                   layout="centered")

# --- styling: large, high-contrast, calm -----------------------------------
st.markdown("""
<style>
  html, body, [class*="css"] { font-size: 18px; }
  .big-pass { background:#1b7f3b; color:white; padding:18px; border-radius:10px;
              font-size:26px; font-weight:700; text-align:center; }
  .big-fail { background:#b3261e; color:white; padding:18px; border-radius:10px;
              font-size:26px; font-weight:700; text-align:center; }
  .stButton>button { font-size:20px; padding:12px 28px; border-radius:10px; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def _extractor():
    return get_extractor()


extractor = _extractor()

st.title("🏛️ Alcohol Label Verifier")
st.caption(f"Compare a label image to its application. "
           f"Active reader: **{extractor.name}**")

_ICON = {Status.PASS: "✅", Status.FAIL: "❌",
         Status.WARNING: "⚠️", Status.MISSING: "⛔"}


def _render_report(report, extracted, elapsed):
    if report.overall_pass:
        st.markdown(f'<div class="big-pass">✅ PASS — label matches '
                    f'application</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="big-fail">❌ NEEDS REVIEW</div>',
                    unsafe_allow_html=True)
    st.write(f"Checked in **{elapsed} seconds**.")
    if elapsed > 5:
        st.warning("Took longer than the 5-second target — consider the local "
                   "OCR reader or a smaller image.")

    rows = []
    for r in report.results:
        rows.append({
            "": _ICON.get(r.status, ""),
            "Field": r.display_name,
            "Application": r.application_value or "—",
            "On Label": (r.label_value or "—")[:80],
            "Result": r.message,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


tab_single, tab_batch = st.tabs(["Single label", "Batch upload"])

# --- single ----------------------------------------------------------------
with tab_single:
    st.subheader("1. Application details")
    c1, c2 = st.columns(2)
    with c1:
        brand_name = st.text_input("Brand name", "OLD TOM DISTILLERY")
        alcohol_content = st.text_input("Alcohol content", "45% Alc./Vol.")
        bottler_address = st.text_input("Bottler / producer", "")
    with c2:
        class_type = st.text_input("Class / type",
                                   "Kentucky Straight Bourbon Whiskey")
        net_contents = st.text_input("Net contents", "750 mL")
        country_of_origin = st.text_input("Country of origin", "")

    st.subheader("2. Label image")
    up = st.file_uploader("Upload the label photo",
                          type=["png", "jpg", "jpeg", "webp"])
    if up:
        st.image(up, caption="Label to verify", width=320)

    if st.button("✔️ Verify label", type="primary", disabled=up is None):
        application = {
            "brand_name": brand_name, "class_type": class_type,
            "alcohol_content": alcohol_content, "net_contents": net_contents,
            "bottler_address": bottler_address,
            "country_of_origin": country_of_origin,
        }
        with st.spinner("Reading the label…"):
            data = up.getvalue()
            t0 = time.perf_counter()
            extracted = extractor.extract(data)
            elapsed = round(time.perf_counter() - t0, 2)
            report = verify(application, extracted)
        _render_report(report, extracted, elapsed)
        with st.expander("What the reader saw on the label"):
            st.json({k: v for k, v in extracted.items()
                     if not k.startswith("_")})

# --- batch -----------------------------------------------------------------
with tab_batch:
    st.subheader("Upload many labels at once")
    st.caption("For peak-season importers submitting hundreds of labels.")
    bc1, bc2 = st.columns(2)
    with bc1:
        b_brand = st.text_input("Brand name (applies to all)", "")
        b_abv = st.text_input("Alcohol content (applies to all)", "")
    with bc2:
        b_type = st.text_input("Class / type (applies to all)", "")
        b_net = st.text_input("Net contents (applies to all)", "")

    ups = st.file_uploader("Upload label photos", accept_multiple_files=True,
                           type=["png", "jpg", "jpeg", "webp"], key="batch")

    if st.button("✔️ Verify all", type="primary", disabled=not ups):
        application = {"brand_name": b_brand, "class_type": b_type,
                       "alcohol_content": b_abv, "net_contents": b_net}
        prog = st.progress(0.0)
        rows = []
        for i, f in enumerate(ups):
            extracted = extractor.extract(f.getvalue())
            report = verify(application, extracted)
            rows.append({
                "File": f.filename,
                "Result": "PASS" if report.overall_pass else "NEEDS REVIEW",
                "Issues": report.summary,
            })
            prog.progress((i + 1) / len(ups))
        df = pd.DataFrame(rows)
        n_pass = (df["Result"] == "PASS").sum()
        st.success(f"Done. {n_pass} of {len(df)} passed.")
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button("⬇️ Download results (CSV)",
                           df.to_csv(index=False).encode(),
                           "verification_results.csv", "text/csv")
