"""Build the HousingValuation AI pitch deck (16:9, light editorial theme)."""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "pitch" / "HousingValuation_Deck.pptx"

BG = RGBColor(0xF7, 0xF8, 0xFA)
CARD = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x0F, 0x17, 0x2A)
MUTED = RGBColor(0x55, 0x60, 0x6F)
FAINT = RGBColor(0x94, 0xA0, 0xB0)
BLUE = RGBColor(0x1D, 0x4E, 0xD8)
GREEN = RGBColor(0x0F, 0x7A, 0x5A)
AMBER = RGBColor(0xB4, 0x53, 0x09)
LINE = RGBColor(0xE3, 0xE7, 0xEE)
CHIP = RGBColor(0xEE, 0xF1, 0xF7)

SERIF = "Georgia"
SANS = "Segoe UI"
MONO = "Consolas"

W, H = 13.333, 7.5


def spacing(run, hundredths):
    run.font._rPr.set("spc", str(hundredths))


def new_slide(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    el = bg._element
    el.getparent().remove(el)
    s.shapes._spTree.insert(2, el)
    return s


def tb(slide, x, y, w, h, items, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = it.get("align", PP_ALIGN.LEFT)
        p.line_spacing = it.get("ls", 1.12)
        p.space_before = Pt(it.get("before", 0))
        p.space_after = Pt(it.get("after", 0))
        r = p.add_run()
        r.text = it["t"]
        r.font.size = Pt(it.get("size", 16))
        r.font.bold = it.get("bold", False)
        r.font.italic = it.get("italic", False)
        r.font.name = it.get("font", SANS)
        r.font.color.rgb = it.get("color", INK)
        if it.get("spc"):
            spacing(r, it["spc"])
    return box


def rect(slide, x, y, w, h, fill=None, line=None, radius=None, lw=1.0):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    sh = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        sh.adjustments[0] = radius
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(lw)
    sh.shadow.inherit = False
    return sh


def kicker(slide, text, y=0.55, color=BLUE):
    tb(slide, 0.85, y, 10.5, 0.3, [{"t": text.upper(), "size": 10, "bold": True, "color": color, "spc": 260}])


def rule(slide, y, w=1.05, color=BLUE):
    rect(slide, 0.85, y, w, 0.055, fill=color)


def headline(slide, text, y=1.05, size=42, w=11.4, color=INK, ls=1.06):
    tb(slide, 0.85, y, w, 2.4, [{"t": text, "size": size, "bold": True, "font": SERIF, "color": color, "ls": ls}])


def body(slide, text, y, size=16, w=10.6, color=MUTED, ls=1.38):
    tb(slide, 0.85, y, w, 1.6, [{"t": text, "size": size, "color": color, "ls": ls}])


def footer(slide, n):
    tb(slide, 0.85, 7.04, 9.5, 0.3, [{"t": "HOUSINGVALUATION AI  ·  HERO HOUSING FINTECH CHALLENGE  ·  PROBLEM STATEMENT 1", "size": 8, "color": FAINT, "spc": 170, "bold": True}])
    tb(slide, W - 1.35, 7.04, 0.5, 0.3, [{"t": f"{n:02d}", "size": 9, "color": FAINT, "bold": True, "align": PP_ALIGN.RIGHT}])


def chip(slide, x, y, w, h, text, size=10.5, color=INK, fill=CHIP, bold=True):
    rect(slide, x, y, w, h, fill=fill, line=None, radius=0.5)
    tb(slide, x, y + 0.02, w, h - 0.04, [{"t": text, "size": size, "bold": bold, "color": color, "align": PP_ALIGN.CENTER}], anchor=MSO_ANCHOR.MIDDLE)


def card(slide, x, y, w, h, fill=CARD, line=LINE):
    return rect(slide, x, y, w, h, fill=fill, line=line, radius=0.05, lw=0.9)


def picture(slide, path, x, y, w):
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w))
    pic.line.color.rgb = LINE
    pic.line.width = Pt(0.75)
    return pic


def build():
    prs = Presentation()
    prs.slide_width = Inches(W)
    prs.slide_height = Inches(H)

    # ---------------- 1. TITLE ----------------
    s = new_slide(prs)
    kicker(s, "Automated valuation  ·  Indian residential & commercial  ·  v2.0", y=0.62)
    rule(s, 0.94)
    tb(s, 0.85, 1.24, 6.85, 1.0, [{"t": "HousingValuation AI", "size": 40, "bold": True, "font": SERIF, "ls": 0.95}])
    tb(s, 0.85, 1.94, 6.8, 0.6, [{"t": "A valuation a lender can defend.", "size": 22, "color": MUTED, "font": SERIF, "italic": True}])
    body(s, "An explainable automated valuation engine for Indian property: a point value, a calibrated range, rupee-level drivers, a policy-evaluated lending position and a hash-chained audit trail — returned by one request.", y=2.85, size=15.5, w=6.5, ls=1.45)
    for i, t in enumerate(["8 cities", "64 micro-markets", "8 property types"]):
        chip(s, 0.85 + i * 1.62, 4.62, 1.5, 0.36, t, size=9.5)
    rect(s, 0.85, 5.15, 6.5, 0.012, fill=LINE)
    tb(s, 0.85, 5.32, 6.6, 0.4, [{"t": "TEAM NEXUSSAI", "size": 8.5, "bold": True, "color": FAINT}])
    tb(s, 0.85, 5.55, 6.8, 1.2, [
        {"t": "Abinivesh M  ·  Team Lead", "size": 11, "color": INK},
        {"t": "Abhinivesh K", "size": 11, "color": INK, "before": 2},
        {"t": "Harini E S", "size": 11, "color": INK, "before": 2},
        {"t": "Mrittika S", "size": 11, "color": INK, "before": 2},
        {"t": "housing-valuation-ai.vercel.app  ·  github.com/abinivesh-m", "size": 9.5, "color": FAINT, "before": 5},
    ])

    card(s, 7.85, 1.24, 4.65, 5.16)
    tb(s, 8.2, 1.5, 4.0, 0.3, [{"t": "LIVE VALUATION  ·  KORAMANGALA, BENGALURU", "size": 8, "bold": True, "color": FAINT, "spc": 130}])
    tb(s, 8.2, 1.82, 2.4, 0.4, [{"t": "ESTIMATED VALUE", "size": 8.5, "bold": True, "color": FAINT, "spc": 180}])
    tb(s, 8.2, 2.05, 2.6, 0.8, [{"t": "₹2.08 Cr", "size": 40, "bold": True, "font": SERIF, "color": INK}])
    tb(s, 8.2, 2.78, 4.0, 0.3, [{"t": "₹16,652 / sqft   ·   p10–p90 ₹1.78–₹2.41 Cr", "size": 10, "color": MUTED}])
    rect(s, 8.2, 3.16, 3.9, 0.02, fill=LINE)
    tb(s, 8.2, 3.3, 1.9, 0.3, [{"t": "CONFIDENCE", "size": 8.5, "bold": True, "color": FAINT, "spc": 180}])
    tb(s, 8.2, 3.52, 1.9, 0.4, [{"t": "88%", "size": 22, "bold": True, "color": GREEN}])
    tb(s, 10.2, 3.3, 1.9, 0.3, [{"t": "LATENCY", "size": 8.5, "bold": True, "color": FAINT, "spc": 180}])
    tb(s, 10.2, 3.52, 1.9, 0.4, [{"t": "55 ms", "size": 22, "bold": True, "color": INK}])
    rect(s, 8.2, 4.12, 3.9, 0.02, fill=LINE)
    rect(s, 8.2, 4.3, 3.9, 0.85, fill=RGBColor(0xE9, 0xF5, 0xEF), line=None, radius=0.08)
    tb(s, 8.42, 4.44, 3.5, 0.3, [{"t": "AUTO-APPROVE ON DESKTOP", "size": 10.5, "bold": True, "color": GREEN, "spc": 90}])
    tb(s, 8.42, 4.72, 3.5, 0.3, [{"t": "under 60 seconds, no manual intervention", "size": 9.5, "color": GREEN}])
    tb(s, 8.2, 5.3, 4.05, 0.9, [{"t": "LTV 48.0% requested  ·  ceiling 75.0%  ·  max loan ₹1.34 Cr  ·  grade A", "size": 9, "color": MUTED, "ls": 1.35}])
    rect(s, 8.2, 5.82, 3.95, 0.012, fill=LINE)
    tb(s, 8.2, 5.94, 3.95, 0.3, [{"t": "hash-chained audit entry  ·  model v2.0", "size": 9, "color": FAINT}])
    footer(s, 1)

    # ---------------- 2. PROBLEM ----------------
    s = new_slide(prs)
    kicker(s, "The problem", y=0.55)
    rule(s, 0.9)
    headline(s, "A collateral number\nwith no defence.", y=1.12, size=44)
    body(s, "Most Indian mortgage collateral is still priced by a site visit and a valuer's judgement. The number can be right and still be unusable: no interval, no drivers, no policy.", y=2.62, size=15.5, w=6.6, ls=1.4)
    card(s, 0.85, 3.72, 6.6, 2.2)
    tb(s, 1.15, 3.94, 3.0, 0.3, [{"t": "WHAT A CREDIT FILE ACTUALLY NEEDS", "size": 8.5, "bold": True, "color": BLUE, "spc": 150}])
    for i, t in enumerate([
        "What is it worth — and how sure are we?",
        "Why that number, in rupees, per driver?",
        "Can we act on it, and who signed off?",
    ]):
        tb(s, 1.15, 4.36 + i * 0.48, 5.9, 0.36, [{"t": "—   " + t, "size": 12.5, "color": INK}])
    tb(s, 7.9, 2.62, 4.6, 0.3, [{"t": "WHERE IT BREAKS", "size": 8.5, "bold": True, "color": FAINT, "spc": 190}])
    rows = [
        ("Days, not minutes", "A physical visit gates every decision, and a book cannot be re-priced without re-visiting it."),
        ("No receipts", "The report states a value. It rarely states which input moved the value by how much."),
        ("No policy trail", "The decision lives in an email. A post-hoc edit leaves no trace."),
    ]
    for i, (t, d) in enumerate(rows):
        y = 3.0 + i * 1.12
        rect(s, 7.9, y + 0.05, 0.055, 0.72, fill=LINE)
        tb(s, 8.14, y, 4.3, 0.3, [{"t": t, "size": 13, "bold": True}])
        tb(s, 8.14, y + 0.3, 4.25, 0.6, [{"t": d, "size": 10.5, "color": MUTED, "ls": 1.3}])
    footer(s, 2)

    # ---------------- 3. THREE QUESTIONS ----------------
    s = new_slide(prs)
    kicker(s, "The test every valuation must pass", y=0.55)
    rule(s, 0.9)
    headline(s, "Worth. Why. Actionable.", y=1.12, size=40, w=8.0)
    body(s, "Most AVMs stop at the first question. A lender cannot underwrite on a point estimate alone — the second and third decide whether the model is used.", y=1.95, size=15, w=8.7, ls=1.35)
    cols = [
        ("01", "What is it worth?", "A point value plus a p10–p90 range whose coverage is measured, not assumed — 79.1% against a nominal 80%.", "Conformal calibration on out-of-fold residuals"),
        ("02", "Why that number?", "Every driver group priced in rupees, exact and reproducible, plus a comparable-sales cross-check with its adjustment grid.", "Baseline substitution + comps"),
        ("03", "Can we act on it?", "A policy engine turns the value into one of four positions with named checks and reason codes — then writes it to a hash chain.", "RBI/NHB LTV bands, 6 checks"),
    ]
    for i, (n, t, d, foot) in enumerate(cols):
        x = 0.85 + i * 3.95
        card(s, x, 2.95, 3.65, 3.25)
        tb(s, x + 0.32, 3.18, 0.6, 0.3, [{"t": n, "size": 10, "bold": True, "color": BLUE, "spc": 120}])
        tb(s, x + 0.32, 3.44, 3.0, 0.4, [{"t": t, "size": 16, "bold": True, "font": SERIF}])
        tb(s, x + 0.32, 3.94, 3.0, 1.5, [{"t": d, "size": 11.5, "color": MUTED, "ls": 1.4}])
        rect(s, x + 0.32, 5.45, 3.0, 0.012, fill=LINE)
        tb(s, x + 0.32, 5.58, 3.0, 0.4, [{"t": foot, "size": 9.5, "color": FAINT, "italic": True}])
    footer(s, 3)

    # ---------------- 4. PRODUCT ----------------
    s = new_slide(prs)
    kicker(s, "The product", y=0.55)
    rule(s, 0.9)
    headline(s, "One request. Six answers.", y=1.05, size=40)
    body(s, "Paste twenty property attributes. The engine returns a complete, self-describing valuation — nothing is filled in later by a human.", y=1.9, size=14.5, w=7.5, ls=1.3)
    steps = [
        ("01", "Value", "point estimate + ₹/sqft"),
        ("02", "Range", "p10–p90 conformal band"),
        ("03", "Drivers", "₹ per driver group"),
        ("04", "Comps", "8 sales, adjustment grid"),
        ("05", "Decision", "4 policy positions + codes"),
        ("06", "Audit", "hash-chained ledger entry"),
    ]
    for i, (n, t, d) in enumerate(steps):
        x = 0.85 + i * 1.93
        card(s, x, 3.0, 1.78, 1.55)
        tb(s, x + 0.22, 3.16, 0.6, 0.3, [{"t": n, "size": 10, "bold": True, "color": BLUE, "spc": 120}])
        tb(s, x + 0.22, 3.42, 1.45, 0.35, [{"t": t, "size": 14, "bold": True, "font": SERIF}])
        tb(s, x + 0.22, 3.8, 1.45, 0.65, [{"t": d, "size": 9, "color": MUTED, "ls": 1.2}])
    body(s, "The same call works for a single property or a 24-property book. The batch endpoint returns a decision mix and a straight-through rate, which is the number a lender actually tracks.", y=4.85, size=13.5, w=8.2, ls=1.35)
    tb(s, 0.85, 5.68, 3.0, 0.3, [{"t": "SURFACES AND GUARANTEES", "size": 8.5, "bold": True, "color": FAINT, "spc": 180}])
    for i, t in enumerate(["single valuation", "24-property batch", "REST API", "no build step", "no runtime sklearn", "offline fallback"]):
        chip(s, 0.85 + i * 1.85, 5.96, 1.72, 0.4, t, size=9.5)
    tb(s, 0.85, 6.54, 11.4, 0.3, [{"t": "A valuation is complete in the response — the model, the mode and the timestamp travel with it.", "size": 11, "color": MUTED, "italic": True}])
    footer(s, 4)

    # ---------------- 5. PROTOTYPE: VALUATION ----------------
    s = new_slide(prs)
    kicker(s, "Single valuation", y=0.5)
    rule(s, 0.85)
    headline(s, "Every number arrives with its reasons.", y=1.0, size=32, w=11.0)
    picture(s, SHOTS / "hv-shot-01-valuation.png", 0.85, 1.85, 8.15)
    card(s, 9.25, 1.85, 3.25, 4.73)
    tb(s, 9.5, 2.05, 2.8, 0.3, [{"t": "WHAT A CREDIT TEAM SEES", "size": 8.5, "bold": True, "color": FAINT, "spc": 150}])
    tb(s, 9.5, 2.4, 2.8, 4.1, [
        {"t": "₹2.08 Cr", "size": 17, "bold": True, "font": SERIF},
        {"t": "with a p10–p90 band of ₹1.78–₹2.41 Cr", "size": 10, "color": MUTED, "after": 10},
        {"t": "88% confidence", "size": 17, "bold": True, "font": SERIF},
        {"t": "calibrated, not a model self-report", "size": 10, "color": MUTED, "after": 10},
        {"t": "7 driver groups", "size": 17, "bold": True, "font": SERIF},
        {"t": "each priced in rupees, adding up to the value", "size": 10, "color": MUTED, "after": 10},
        {"t": "Auto-approve", "size": 17, "bold": True, "font": SERIF, "color": GREEN},
        {"t": "desktop decision, grade A, no policy breach", "size": 10, "color": MUTED},
    ])
    rect(s, 9.5, 5.78, 2.75, 0.012, fill=LINE)
    tb(s, 9.5, 5.9, 2.75, 0.6, [{"t": "Every value here is in the response body — nothing is typed in by hand.", "size": 8.5, "color": FAINT, "italic": True, "ls": 1.3}])
    footer(s, 5)

    # ---------------- 6. PROTOTYPE: BATCH ----------------
    s = new_slide(prs)
    kicker(s, "Book-level scoring", y=0.5)
    rule(s, 0.85)
    headline(s, "A book, priced in one request.", y=1.0, size=32, w=11.0)
    picture(s, SHOTS / "hv-shot-02-portfolio.png", 0.85, 1.9, 5.6)
    stats = [
        ("24", "properties scored", "one POST to /batch, no per-file handling"),
        ("54%", "straight-through", "cleared a desktop decision with no site visit"),
        ("₹37.38 Cr", "book value", "sum of point estimates across the slice"),
        ("42%", "referred to inspection", "routed, never silently approved"),
    ]
    for i, (n, t, d) in enumerate(stats):
        x = 6.75 + (i % 2) * 2.92
        y = 1.9 + (i // 2) * 2.28
        card(s, x, y, 2.78, 2.15)
        tb(s, x + 0.3, y + 0.26, 2.2, 0.5, [{"t": n, "size": 26, "bold": True, "font": SERIF}])
        tb(s, x + 0.3, y + 0.88, 2.2, 0.25, [{"t": t, "size": 10, "bold": True, "color": GREEN, "spc": 60}])
        tb(s, x + 0.3, y + 1.18, 2.2, 0.8, [{"t": d, "size": 9.5, "color": MUTED, "ls": 1.3}])
    footer(s, 6)

    # ---------------- 7. HOW IT WORKS ----------------
    s = new_slide(prs)
    kicker(s, "How it is built", y=0.55)
    rule(s, 0.9)
    headline(s, "One request, six honest stages.", y=1.05, size=38)
    body(s, "A valuation fans out to a model, a comparable set and a geo lookup, then reconciles all three. No database, no worker, no hidden state between calls.", y=1.9, size=14, w=7.6, ls=1.32)
    stages = [
        ("1", "Validate the record", "20 fields, typed and range-checked"),
        ("2", "Price the property", "GBM on log price, JSON trees"),
        ("3", "Widen for honesty", "conformal p10–p90, unseen-market flag"),
        ("4", "Attribute the value", "baseline substitution, ₹ per group"),
        ("5", "Cross-check with comps", "adjustment grid, recency weighted"),
        ("6", "Evaluate policy", "LTV band, confidence haircut, codes"),
    ]
    for i, (n, t, d) in enumerate(stages):
        col, row = i % 2, i // 2
        x = 0.85 + col * 3.9
        y = 2.9 + row * 1.24
        card(s, x, y, 3.6, 1.04)
        tb(s, x + 0.24, y + 0.13, 0.4, 0.3, [{"t": n, "size": 11, "bold": True, "color": BLUE}])
        tb(s, x + 0.54, y + 0.11, 2.95, 0.3, [{"t": t, "size": 12.5, "bold": True}])
        tb(s, x + 0.54, y + 0.49, 2.95, 0.4, [{"t": d, "size": 9.5, "color": MUTED}])
    card(s, 8.95, 2.9, 3.55, 3.5, fill=CHIP)
    tb(s, 9.2, 3.1, 3.0, 0.3, [{"t": "THE INVARIANT", "size": 8.5, "bold": True, "color": BLUE, "spc": 180}])
    tb(s, 9.2, 3.44, 3.05, 2.7, [
        {"t": "The number and its caveats ship together.", "size": 12.5, "bold": True, "ls": 1.3},
        {"t": "An unseen micro-market widens the interval and lowers confidence — it never borrows a neighbouring locality's certainty.", "size": 11, "color": MUTED, "ls": 1.35, "before": 8},
        {"t": "Geo enrichment is async: if the lookup fails, the report says so and falls back to application distances.", "size": 11, "color": MUTED, "ls": 1.35, "before": 8},
    ])
    footer(s, 7)

    # ---------------- 8. ACCURACY ----------------
    s = new_slide(prs)
    kicker(s, "Measured accuracy", y=0.55)
    rule(s, 0.9)
    headline(s, "Better than the rate card.\nAnd stated honestly.", y=1.05, size=28)
    tb(s, 0.85, 2.2, 3.3, 0.3, [{"t": "MODEL  ·  IDENTICAL TEST ROWS", "size": 8.5, "bold": True, "color": FAINT, "spc": 140}])
    tb(s, 4.75, 2.2, 1.4, 0.3, [{"t": "MAPE", "size": 8.5, "bold": True, "color": FAINT, "spc": 140}])
    tb(s, 6.35, 2.2, 1.1, 0.3, [{"t": "R²", "size": 8.5, "bold": True, "color": FAINT, "spc": 140}])
    tb(s, 7.65, 2.2, 1.6, 0.3, [{"t": "WITHIN ±10%", "size": 8.5, "bold": True, "color": FAINT, "spc": 140}])
    tb(s, 10.4, 2.2, 2.0, 0.3, [{"t": "READ", "size": 8.5, "bold": True, "color": FAINT, "spc": 140}])
    rows = [
        ("Global median ₹/sqft × area", "42.1%", "0.35", "16%", "No locality signal at all", False),
        ("Locality × type median — today's rate card", "12.9%", "0.95", "47%", "The benchmark lenders actually run", False),
        ("Ridge hedonic regression, same features", "26.0%", "0.68", "26%", "Linear model, same inputs", False),
        ("This engine — gradient boosting", "11.2%", "0.944", "54%", "1.7 pp better than the rate card", True),
    ]
    for i, (name, mape, r2, w10, read, hi) in enumerate(rows):
        y = 2.48 + i * 0.74
        if hi:
            rect(s, 0.85, y - 0.09, 11.6, 0.7, fill=CHIP, radius=0.12)
        tb(s, 1.05, y + 0.06, 3.6, 0.3, [{"t": name, "size": 10.5, "bold": hi, "color": INK if hi else MUTED}])
        tb(s, 4.75, y + 0.02, 1.4, 0.35, [{"t": mape, "size": 14 if hi else 12, "bold": hi, "color": GREEN if hi else INK}])
        tb(s, 6.35, y + 0.04, 1.1, 0.3, [{"t": r2, "size": 11.5, "color": MUTED}])
        tb(s, 7.65, y + 0.04, 1.4, 0.3, [{"t": w10, "size": 11.5, "color": MUTED}])
        tb(s, 9.35, y + 0.05, 3.1, 0.3, [{"t": read, "size": 9.5, "color": FAINT}])
        if i < 3:
            rect(s, 0.85, y + 0.58, 11.6, 0.008, fill=LINE)
    tb(s, 0.85, 5.52, 5.6, 0.3, [{"t": "THE NUMBER THAT KEEPS US HONEST", "size": 8.5, "bold": True, "color": BLUE, "spc": 160}])
    tb(s, 0.85, 5.8, 5.7, 0.7, [{"t": "Grouped 5-fold CV by locality: 23.5% MAPE, worst fold 29.7%. Error roughly doubles when a micro-market has no training history — which is exactly when the interval widens and confidence drops.", "size": 10.5, "color": MUTED, "ls": 1.3}])
    tb(s, 6.9, 5.52, 5.6, 0.3, [{"t": "INTERVAL COVERAGE", "size": 8.5, "bold": True, "color": BLUE, "spc": 160}])
    tb(s, 6.9, 5.8, 5.6, 0.7, [{"t": "79.1% empirical p10–p90 coverage against a nominal 80%, median band width 35.2%. Calibration is checked, not asserted — and a production rollback triggers if rolling coverage falls below 72%.", "size": 10.5, "color": MUTED, "ls": 1.3}])
    footer(s, 8)

    # ---------------- 9. EXPLAINABILITY ----------------
    s = new_slide(prs)
    kicker(s, "Explainability", y=0.55)
    rule(s, 0.9)
    headline(s, "The value decomposes\ninto rupees.", y=1.05, size=36)
    body(s, "Baseline substitution: swap one feature group at a time against the typical property in the micro-market, re-run the model, and price the difference. Exact, model-agnostic, reproducible — and it adds up to the estimate.", y=2.35, size=13.5, w=6.3, ls=1.35)
    drivers = [
        ("Property profile", "+₹20.7 L", 1.0, GREEN),
        ("Connectivity", "−₹7.3 L", 0.35, AMBER),
        ("Age & condition", "+₹2.7 L", 0.13, GREEN),
        ("Neighbourhood safety", "+₹2.0 L", 0.1, GREEN),
        ("Size & layout", "−₹35,000", 0.03, AMBER),
        ("Building & amenities", "+₹10,000", 0.02, GREEN),
    ]
    tb(s, 0.85, 3.92, 4.6, 0.3, [{"t": "DRIVER ATTRIBUTION  ·  ₹2.08 CR", "size": 8.5, "bold": True, "color": BLUE, "spc": 160}])
    for i, (name, val, frac, col) in enumerate(drivers):
        y = 4.3 + i * 0.38
        tb(s, 0.85, y, 2.3, 0.3, [{"t": name, "size": 10.5}])
        rect(s, 3.2, y + 0.1, 2.4 * frac, 0.12, fill=col)
        tb(s, 5.72, y, 1.3, 0.3, [{"t": val, "size": 10.5, "bold": True, "color": col, "align": PP_ALIGN.RIGHT}])
    card(s, 7.5, 2.35, 5.0, 4.2)
    tb(s, 7.8, 2.55, 4.4, 0.3, [{"t": "EXPLANATION, NOT DECORATION", "size": 8.5, "bold": True, "color": BLUE, "spc": 160}])
    tb(s, 7.8, 2.9, 4.4, 3.4, [
        {"t": "Every rupee is traceable to an input field.", "size": 12.5, "bold": True, "ls": 1.3},
        {"t": "No SHAP sampling, no surrogate model, no post-hoc approximation — the same model that priced the property produced the attribution.", "size": 11, "color": MUTED, "ls": 1.35, "before": 8},
        {"t": "The comparable-sales engine runs beside it with an explicit adjustment grid: age 0.9%/yr, floor ratio 6%/unit, furnishing 0/3.5/7.5%, size elasticity −0.18, market drift 0.4%/month. Model and comps agree within 6.3% on this file.", "size": 11, "color": MUTED, "ls": 1.35, "before": 8},
        {"t": "When they disagree, the report says so instead of hiding the spread.", "size": 11, "color": MUTED, "ls": 1.35, "before": 8},
    ])
    footer(s, 9)

    # ---------------- 10. LENDING ----------------
    s = new_slide(prs)
    kicker(s, "The lending layer", y=0.55)
    rule(s, 0.9)
    headline(s, "A policy, not a guess.", y=1.05, size=40)
    body(s, "The engine evaluates collateral risk; it does not make a credit decision. Every rule is named, evaluated and returned with a pass / warn / fail status and a machine-readable code, so an override is logged and replayable.", y=1.9, size=14, w=7.6, ls=1.32)
    outcomes = [
        ("AUTO-APPROVE DESKTOP", "confidence ≥ 72%, LTV ≤ ceiling × 0.95, no warnings", GREEN),
        ("APPROVE WITH CONDITIONS", "LTV within ceiling, confidence ≥ 60%", GREEN),
        ("REFER PHYSICAL VALUATION", "any hard check failed", AMBER),
        ("REFER CREDIT OFFICER", "LTV above ceiling, or confidence < 60%", AMBER),
    ]
    for i, (t, d, col) in enumerate(outcomes):
        y = 2.9 + i * 0.92
        card(s, 0.85, y, 7.5, 0.78)
        rect(s, 0.97, y + 0.2, 0.05, 0.38, fill=col)
        tb(s, 1.18, y + 0.14, 4.0, 0.3, [{"t": t, "size": 11.5, "bold": True, "color": col, "spc": 40}])
        tb(s, 1.18, y + 0.44, 6.9, 0.3, [{"t": d, "size": 10, "color": MUTED}])
    card(s, 8.75, 2.9, 3.75, 3.55, fill=CHIP)
    tb(s, 9.0, 3.1, 3.3, 0.3, [{"t": "RBI / NHB LTV CEILINGS", "size": 8.5, "bold": True, "color": BLUE, "spc": 160}])
    for i, (band, ltv) in enumerate([("≤ ₹30 lakh", "90%"), ("₹30–75 lakh", "80%"), ("above ₹75 lakh", "75%")]):
        y = 3.5 + i * 0.5
        tb(s, 9.0, y, 2.2, 0.3, [{"t": band, "size": 11.5}])
        tb(s, 11.2, y, 1.1, 0.3, [{"t": ltv, "size": 12.5, "bold": True, "align": PP_ALIGN.RIGHT}])
        rect(s, 9.0, y + 0.36, 3.3, 0.01, fill=LINE)
    tb(s, 9.0, 5.15, 3.3, 1.2, [{"t": "Caps are only ever tightened, never raised. A 0–20% confidence haircut applies on top, and the recommended loan is computed on the p10 value — not the point estimate.", "size": 10, "color": MUTED, "ls": 1.35}])
    tb(s, 0.85, 6.55, 11.4, 0.3, [{"t": "On the reference file: requested LTV 48.0% against a 75.0% ceiling → auto-approve, grade A, ₹1.34 Cr maximum loan.", "size": 10.5, "color": MUTED, "italic": True}])
    footer(s, 10)

    # ---------------- 11. GOVERNANCE ----------------
    s = new_slide(prs)
    kicker(s, "Governance", y=0.5)
    rule(s, 0.85)
    headline(s, "Edits are detectable.", y=1.0, size=32, w=11.0)
    picture(s, SHOTS / "hv-shot-04-governance.png", 0.85, 1.82, 7.9)
    card(s, 9.0, 1.82, 3.5, 4.84)
    tb(s, 9.25, 2.02, 3.0, 0.3, [{"t": "WHAT A VALIDATOR ASKS FOR", "size": 8, "bold": True, "color": FAINT, "spc": 120}])
    tb(s, 9.25, 2.35, 3.05, 4.1, [
        {"t": "Hash chain", "size": 13, "bold": True},
        {"t": "every valuation re-hashes the previous entry; one edited byte breaks the chain", "size": 10, "color": MUTED, "after": 12},
        {"t": "Replay", "size": 13, "bold": True},
        {"t": "decision, inputs, model version and confidence are stored with the number", "size": 10, "color": MUTED, "after": 12},
        {"t": "Drift", "size": 13, "bold": True},
        {"t": "re-fit is triggered when PSI exceeds 0.2 on a key feature", "size": 10, "color": MUTED, "after": 12},
        {"t": "Fairness", "size": 13, "bold": True},
        {"t": "no borrower demographic attribute is an input to the valuation", "size": 10, "color": MUTED, "after": 12},
        {"t": "Provenance", "size": 13, "bold": True},
        {"t": "the corpus is declared synthetic, and every report carries that disclaimer", "size": 10, "color": MUTED},
    ])
    footer(s, 11)

    # ---------------- 12. DATA STRATEGY ----------------
    s = new_slide(prs)
    kicker(s, "Data strategy", y=0.55)
    rule(s, 0.9)
    headline(s, "What is live, and what is planned.", y=1.05, size=36)
    body(s, "This build trains on a documented parametric corpus, not licensed transaction data. Every metric in this deck is measured on that corpus. Here is exactly what is wired in today and what a production deployment adds.", y=1.9, size=14, w=11.2, ls=1.3)
    items = [
        ("Registry transactions", "Sale deeds from state portals, deduplicated and geocoded", False),
        ("Government rate cards", "Circle / ready-reckoner tables per village and zone", False),
        ("Property attributes", "Area, layout, age, floor, tenure, occupancy, quality", True),
        ("Satellite & built-up area", "Roof-footprint delineation and change detection", False),
        ("Geospatial POI density", "OpenStreetMap Overpass counts within 1.5 km, live", True),
        ("Market & infrastructure", "Price indices and pipeline as market-drift features", False),
    ]
    for i, (t, d, live) in enumerate(items):
        col, row = i % 2, i // 2
        x = 0.85 + col * 5.95
        y = 2.95 + row * 1.18
        card(s, x, y, 5.7, 1.0)
        tb(s, x + 0.3, y + 0.16, 3.4, 0.3, [{"t": t, "size": 12.5, "bold": True}])
        tb(s, x + 0.3, y + 0.5, 4.0, 0.4, [{"t": d, "size": 9.5, "color": MUTED, "ls": 1.2}])
        if live:
            chip(s, x + 4.35, y + 0.32, 1.1, 0.34, "LIVE", size=8, color=GREEN, fill=RGBColor(0xE9, 0xF5, 0xEF))
        else:
            chip(s, x + 4.35, y + 0.32, 1.1, 0.34, "PLANNED", size=8, color=AMBER, fill=RGBColor(0xFB, 0xF1, 0xE4))
    tb(s, 0.85, 6.5, 11.6, 0.4, [{"t": "Loading a registry feed changes the corpus, not the pipeline: the same calibration, attribution and policy code runs unchanged.", "size": 11, "color": MUTED, "italic": True}])
    footer(s, 12)

    # ---------------- 13. ENGINEERING ----------------
    s = new_slide(prs)
    kicker(s, "Engineering", y=0.55)
    rule(s, 0.9)
    headline(s, "Built to survive a deploy.", y=1.05, size=38)
    cards = [
        ("55 ms", "median valuation", "warm, single vCPU"),
        ("29", "tests", "policy, model, audit, API"),
        ("0.0e+00", "tree drift", "JSON trees reproduce sklearn exactly"),
        ("1", "container", "no build step, no worker"),
    ]
    for i, (n, t, d) in enumerate(cards):
        x = 0.85 + i * 3.0
        card(s, x, 2.0, 2.8, 1.5)
        tb(s, x + 0.28, 2.1, 2.3, 0.5, [{"t": n, "size": 25, "bold": True, "font": SERIF, "color": BLUE if i == 0 else INK}])
        tb(s, x + 0.28, 2.64, 2.3, 0.3, [{"t": t, "size": 10.5, "bold": True, "color": GREEN, "spc": 50}])
        tb(s, x + 0.28, 2.94, 2.3, 0.5, [{"t": d, "size": 9, "color": MUTED, "ls": 1.25}])
    tb(s, 0.85, 3.8, 5.5, 0.3, [{"t": "THE BUG THAT SHAPED THE BUILD", "size": 8.5, "bold": True, "color": BLUE, "spc": 160}])
    tb(s, 0.85, 4.1, 5.6, 1.2, [{"t": "The first deployment failed with ModuleNotFoundError: No module named '_loss' — a joblib pickle written by scikit-learn 1.8 and read by an older runtime.", "size": 11, "color": MUTED, "ls": 1.4}])
    tb(s, 6.5, 3.8, 5.9, 0.3, [{"t": "THE FIX", "size": 8.5, "bold": True, "color": BLUE, "spc": 160}])
    tb(s, 6.5, 4.1, 5.95, 1.3, [{"t": "The model is exported to flat JSON tree arrays and evaluated by a pure-numpy module. No scikit-learn at runtime, no pickle, no version drift. A round-trip test asserts the exported trees reproduce the training predictions exactly over 250 rows (max |Δ log price| = 0.0e+00), and training refuses to write artifacts if it does not.", "size": 11, "color": MUTED, "ls": 1.4}])
    rect(s, 0.85, 5.56, 11.6, 0.012, fill=LINE)
    claims = [
        ("Deterministic", "The same record returns the same value, the same driver split and the same decision — asserted by test, not convention."),
        ("Fail-closed", "Training refuses to publish when the round-trip check fails, so a broken artifact cannot reach the API."),
        ("Stateless", "One process, no database, no worker: the hash chain is the only state, and it is append-only."),
    ]
    for i, (t, d) in enumerate(claims):
        x = 0.85 + i * 4.0
        tb(s, x, 5.76, 3.6, 0.3, [{"t": t, "size": 11.5, "bold": True}])
        tb(s, x, 6.08, 3.6, 0.8, [{"t": d, "size": 9.5, "color": MUTED, "ls": 1.35}])
    footer(s, 13)

    # ---------------- 14. MARKET ----------------
    s = new_slide(prs)
    kicker(s, "Who pays", y=0.55)
    rule(s, 0.9)
    headline(s, "The buyer already has the problem.", y=1.05, size=36)
    body(s, "Every lender that takes property as collateral needs a defensible number, a policy position and an audit trail. The wedge is the book, not the single file.", y=1.95, size=14.5, w=7.4, ls=1.32)
    rows = [
        ("HFCs & NBFCs", "Highest volume, thinnest valuer bench, fastest to adopt a desktop decision."),
        ("Banks & co-operative lenders", "Need policy alignment and an audit trail before a model can touch collateral."),
        ("Valuation & due-diligence firms", "Use the engine as a first pass, then spend human time on the exceptions."),
    ]
    for i, (t, d) in enumerate(rows):
        y = 2.95 + i * 1.15
        card(s, 0.85, y, 7.2, 1.0)
        tb(s, 1.1, y + 0.16, 2.6, 0.3, [{"t": t, "size": 12.5, "bold": True}])
        tb(s, 1.1, y + 0.48, 6.7, 0.4, [{"t": d, "size": 10, "color": MUTED}])
    card(s, 8.35, 2.95, 4.15, 3.4, fill=CHIP)
    tb(s, 8.6, 3.15, 3.6, 0.3, [{"t": "HOW IT MAKES MONEY", "size": 8.5, "bold": True, "color": BLUE, "spc": 160}])
    tb(s, 8.6, 3.5, 3.65, 2.2, [
        {"t": "Per-valuation API", "size": 13, "bold": True},
        {"t": "metered on successful checks, with a free tier for pilots", "size": 10.5, "color": MUTED, "after": 14},
        {"t": "Lender platform licence", "size": 13, "bold": True},
        {"t": "batch book scoring, policy tuning, SSO and roles", "size": 10.5, "color": MUTED, "after": 14},
        {"t": "Audit & compliance module", "size": 13, "bold": True},
        {"t": "hash-chained evidence packs for internal and regulatory review", "size": 10.5, "color": MUTED},
    ])
    rect(s, 8.6, 5.72, 3.65, 0.012, fill=LINE)
    tb(s, 8.6, 5.84, 3.65, 0.5, [{"t": "Priced per file, not as a share of loan value.", "size": 9.5, "color": FAINT, "italic": True}])
    tb(s, 0.85, 6.55, 11.5, 0.3, [{"t": "Start with one product line at one lender: auto-finance or LAP, where turnaround time is already the constraint.", "size": 10.5, "color": MUTED, "italic": True}])
    footer(s, 14)

    # ---------------- 15. TEAM + ASK ----------------
    s = new_slide(prs)
    kicker(s, "The ask", y=0.55)
    rule(s, 0.9)
    headline(s, "Give us a book,\nnot a sandbox.", y=1.12, size=42)
    asks = [
        ("500", "live files", "a pilot slice with registry data, to re-measure every number on real deeds"),
        ("1", "registry sandbox", "read access to one state portal and circle-rate table"),
        ("90 days", "to first decision", "a joint target for straight-through rate on a real book"),
    ]
    for i, (n, t, d) in enumerate(asks):
        x = 0.85 + i * 3.95
        card(s, x, 3.0, 3.65, 1.95)
        tb(s, x + 0.32, 3.2, 3.0, 0.5, [{"t": n, "size": 22, "bold": True, "font": SERIF, "color": BLUE}])
        tb(s, x + 0.32, 3.66, 3.0, 0.3, [{"t": t, "size": 12, "bold": True}])
        tb(s, x + 0.32, 3.98, 3.0, 0.85, [{"t": d, "size": 10, "color": MUTED, "ls": 1.3}])
    rect(s, 0.85, 5.28, 11.6, 0.012, fill=LINE)
    tb(s, 0.85, 5.48, 5.6, 1.5, [
        {"t": "Team NexussAI", "size": 9, "bold": True, "color": FAINT},
        {"t": "Abinivesh M  ·  Team Lead", "size": 11.5, "color": INK, "before": 6},
        {"t": "Abhinivesh K", "size": 11.5, "color": INK, "before": 2},
        {"t": "Harini E S", "size": 11.5, "color": INK, "before": 2},
        {"t": "Mrittika S", "size": 11.5, "color": INK, "before": 2},
        {"t": "housing-valuation-ai.vercel.app", "size": 10, "color": FAINT, "before": 6},
    ])
    tb(s, 7.2, 5.48, 5.3, 1.2, [
        {"t": "“A valuation that cannot explain itself", "size": 13.5, "font": SERIF, "italic": True},
        {"t": "is a number nobody can lend against.”", "size": 13.5, "font": SERIF, "italic": True},
    ])
    footer(s, 15)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print("saved:", OUT, OUT.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    build()
