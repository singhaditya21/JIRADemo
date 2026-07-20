#!/usr/bin/env python3
"""Render the control tower: one Jira read, one self-contained HTML file.

WHAT THIS IS
------------
`python3 -m app.cli tower --project OPS --days 90` reads every issue in the
project ONCE (app/store.fetch), computes every panel locally
(app/analytics.compute_all), and writes a single HTML file that opens from
file:// with no server, no CDN, no font download and no network of any kind.

WHY IT EXISTS - the argument the file has to make
--------------------------------------------------
Jira's own dashboards cannot do three things this page does, and if this file
only reproduced what a gadget already shows it would have failed:

  1. TREND A CUSTOM DATETIME FIELD. Jira stores no history for `Reported At`, so
     no gadget can bucket by it and none can rewind a backlog to what it was six
     weeks ago. Panel 1's aged-backlog sparkline is reconstructed from the
     timeline (analytics.backlog_as_of) - a stock evaluated at each week
     boundary, not a flow counted inside a bucket.
  2. NORMALISE A RATE PER ANALYST WITH A DISPERSION BAND. Panel 3 is PILOT.md
     exit criterion 6 ("no analyst diverges > 2 sigma") rendered as a judgement,
     with a small-sample floor so one new starter's first three tickets cannot
     slacken the yardstick.
  3. PAIR TWO METRICS SO GAMING ONE EXPOSES THE OTHER. Panel 2 puts first-time
     resolution against reopen rate over a SHARED denominator. Closing early
     lifts the first and wrecks the second; neither can be moved alone.

LAYER RULES (enforced - see tools/check_consistency.py)
-------------------------------------------------------
Imports shared/ and app/ only. Never jira_config, never fixtures, never a
build artifact under jira_config/state/. Fields are resolved by NAME through
shared/fields.py. READ-ONLY against Jira: the only call this module's data path
makes is app.store.fetch, whose sole verb is a POST to Jira's *read* endpoint
/rest/api/3/search/jql.

STRUCTURE, AND WHY IT IS SPLIT THIS WAY
---------------------------------------
    run(args)                 the only function that touches Jira or the disk
      +- build_model(...)     pure: store rows -> a dict of everything
      +- render(model)        pure: dict -> an HTML string

`build_model` and `render` take no Jira handle and perform no IO, so the whole
page is testable offline against a frozen snapshot in milliseconds. That is also
what keeps app/ read-only against Jira by construction rather than by promise.

RENDERING RULES THIS MODULE HOLDS TO
------------------------------------
  * ALL geometry is computed in Python. JavaScript never computes a coordinate.
    The file renders correctly and completely with JS disabled; script adds the
    theme toggle, table sorting, tooltips and the table twins' disclosure only.
  * No literal colour appears in emitted markup. Every fill and stroke is a
    var(--token), which is what makes the theme switch free and total.
  * No dual-axis plot. Panels 2 and 4 are two stacked panes sharing an x-axis,
    each with its own baseline and its own labelled scale. Overlaying two
    unrelated ranges on one frame invents a correlation.
  * Every rate is printed with its numerator and denominator. 78.9% over 388
    adjudicated tickets is a different claim from 78.9% over 12.
  * Every target is a PLACEHOLDER and is labelled as one on the page, in the
    tile, and in the footer. They are invented (CLAIMS.md #14/#15) and exist to
    be replaced from a measured baseline.
  * A weekly rate whose denominator is below analytics.MIN_WEEK_DENOM is not
    plotted. The line BREAKS. "Too few tickets to state a rate" is a different
    fact from 0%, and the partial weeks at either end of any window are the most
    eye-catching and most meaningless points on the chart.
  * `Reported At` is the only time axis anywhere. Jira's `created` appears in
    exactly one place - a footer line stating that it holds one distinct date
    across the whole project, which is why it was rejected.

Python 3.9. Standard library only. No f-string contains a backslash.
"""

import argparse
import datetime
import json
import math
import os
from html import escape as _h
from pathlib import Path

from shared.jira_client import Jira, log, require_env, warn
from shared import domain as D
from shared import fields as FIELDS
from app import analytics as A
from app import store as S


# ===========================================================================
# Markup toolkit
# ===========================================================================

NL = "\n"


def attrs(**kw):
    """dict -> ' k="v"'. Underscores become dashes; None drops the attribute.

    A trailing underscore is stripped first, so `class_` and `for_` are
    expressible without colliding with Python keywords.
    """
    out = []
    for k, v in kw.items():
        if v is None:
            continue
        name = k.rstrip("_").replace("_", "-")
        out.append('%s="%s"' % (name, _h(str(v), quote=True)))
    return (" " + " ".join(out)) if out else ""


def el(tag, *children, **kw):
    inner = "".join(c for c in children if c)
    if inner:
        return "<%s%s>%s</%s>" % (tag, attrs(**kw), inner, tag)
    return "<%s%s/>" % (tag, attrs(**kw))


def htag(tag, *children, **kw):
    """Like el(), but always emits a closing tag - HTML has no self-closing div."""
    return "<%s%s>%s</%s>" % (tag, attrs(**kw), "".join(c for c in children if c), tag)


def text(s, x, y, **kw):
    return "<text%s>%s</text>" % (attrs(x=x, y=y, **kw), _h(str(s)))


def linear(d0, d1, r0, r1):
    """Domain -> range. A degenerate domain maps to the range midpoint, never NaN."""
    span = float(d1 - d0) or 1.0

    def f(v):
        return r0 + (float(v) - d0) * (r1 - r0) / span
    return f


def polyline_d(pts):
    head = "M %.2f %.2f" % pts[0]
    return head + "".join(" L %.2f %.2f" % p for p in pts[1:])


def area_d(pts, baseline):
    return polyline_d(pts) + " L %.2f %.2f L %.2f %.2f Z" % (
        pts[-1][0], baseline, pts[0][0], baseline)


def rrect(x, y, w, h, r, **kw):
    """Vertical bar: rounded at the DATA end (top), square on the baseline."""
    h = max(0.0, float(h))
    w = max(0.0, float(w))
    r = max(0.0, min(float(r), w / 2.0, h))
    d = ("M %.2f %.2f L %.2f %.2f Q %.2f %.2f %.2f %.2f "
         "L %.2f %.2f Q %.2f %.2f %.2f %.2f L %.2f %.2f Z") % (
        x, y + h, x, y + r, x, y, x + r, y,
        x + w - r, y, x + w, y, x + w, y + r, x + w, y + h)
    return "<path%s/>" % attrs(d=d, **kw)


def hrect(x, y, w, h, r, **kw):
    """Horizontal bar: rounded at the DATA end (right), square at the axis."""
    w = max(0.0, float(w))
    h = max(0.0, float(h))
    r = max(0.0, min(float(r), w, h / 2.0))
    d = ("M %.2f %.2f L %.2f %.2f Q %.2f %.2f %.2f %.2f "
         "L %.2f %.2f Q %.2f %.2f %.2f %.2f L %.2f %.2f Z") % (
        x, y, x + w - r, y, x + w, y, x + w, y + r,
        x + w, y + h - r, x + w, y + h, x + w - r, y + h, x, y + h)
    return "<path%s/>" % attrs(d=d, **kw)


def lrect(x, y, w, h, r, **kw):
    """Horizontal bar rounded at the LEFT end only - the outer end of a stack."""
    w = max(0.0, float(w))
    h = max(0.0, float(h))
    r = max(0.0, min(float(r), w, h / 2.0))
    d = ("M %.2f %.2f L %.2f %.2f L %.2f %.2f L %.2f %.2f "
         "Q %.2f %.2f %.2f %.2f L %.2f %.2f Q %.2f %.2f %.2f %.2f Z") % (
        x + r, y, x + w, y, x + w, y + h, x + r, y + h,
        x, y + h, x, y + h - r, x, y + r, x, y, x + r, y)
    return "<path%s/>" % attrs(d=d, **kw)


def runs(pairs):
    """[(x, y or None)] -> [[(x, y), ...], ...], splitting on every None.

    This is how a rate that abstains renders as a BREAK in the line rather than
    a plunge to zero. See analytics.rate_point for why abstaining matters.
    """
    out, cur = [], []
    for x, y in pairs:
        if y is None:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append((x, float(y)))
    if cur:
        out.append(cur)
    return out


# ---------------------------------------------------------------------------
# Scales and formatting
# ---------------------------------------------------------------------------

def nice_step(raw):
    """The 1 / 2 / 2.5 / 5 / 10 step at or above `raw`."""
    if raw <= 0:
        return 1.0
    mag = 10.0 ** math.floor(math.log10(raw))
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        if raw <= mult * mag + 1e-12:
            return mult * mag
    return 10.0 * mag


def ticks_for(vmin, vmax, count=4, clamp_pct=False):
    """`count`-ish rounded ticks covering [vmin, vmax]. Never empty, never NaN."""
    if vmax <= vmin:
        vmax = vmin + 1.0
    step = nice_step((vmax - vmin) / float(count))
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    if clamp_pct:
        lo = max(0.0, lo)
        hi = min(100.0, hi) if hi > 100.0 else hi
    out, v = [], lo
    while v <= hi + 1e-9:
        out.append(round(v, 6))
        v += step
    return out


def f1(v):
    return "%.1f" % float(v)


def pctlab(v, dp=1):
    if v is None:
        return "n/a"
    return ("%." + str(dp) + "f%%") % float(v)


def intlab(v):
    return "%d" % int(round(float(v)))


def ratio(num, den):
    """'215/348' - the denominator every percentage on this page carries."""
    if num is None or den is None:
        return ""
    return "%d/%d" % (num, den)


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def daylab(d):
    """'24 Apr'. Built by hand: strftime('%-d') is not portable."""
    return "%d %s" % (d.day, MONTHS[d.month - 1])


def datelab(d):
    return "%d %s %d" % (d.day, MONTHS[d.month - 1], d.year)


def iso_to_date(s):
    y, m, dd = s.split("-")
    return datetime.date(int(y), int(m), int(dd))


# ---------------------------------------------------------------------------
# The shared plot frame
# ---------------------------------------------------------------------------

PAD = {"t": 16, "r": 18, "b": 30, "l": 46}

# Design width per column span at --measure 1180. Rendered scale is clamped to
# roughly [0.86, 1.00] by a min-width the generator writes inline, so a 12px
# axis tick never renders below ~10.3px and a narrow viewport scrolls the CHART
# rather than the page body.
CHART_W = {12: 1132, 8: 748, 7: 660, 6: 552, 5: 452, 4: 356}


def gridlines(x0, x1, tick_px, label):
    """Hairline gridlines plus right-aligned y tick labels. Never dashed."""
    parts = []
    for v, y in tick_px:
        parts.append(el("line", x1="%.2f" % x0, y1="%.2f" % y,
                        x2="%.2f" % x1, y2="%.2f" % y,
                        stroke="var(--c-grid)", stroke_width=1))
        parts.append(text(label(v), "%.2f" % (x0 - 8), "%.2f" % (y + 4),
                          text_anchor="end", font_family="var(--mono)",
                          font_size=12, fill="var(--c-mute)",
                          style="font-variant-numeric:tabular-nums"))
    return "".join(parts)


def baseline(x0, x1, y):
    return el("line", x1="%.2f" % x0, y1="%.2f" % y, x2="%.2f" % x1,
              y2="%.2f" % y, stroke="var(--c-axis)", stroke_width=1)


def week_ticks(weeks, sx, plot_w, y):
    """X labels, thinned so they cannot collide, always including the last."""
    n = len(weeks)
    if n == 0:
        return ""
    every = max(1, int(math.ceil(n * 46.0 / max(plot_w, 1))))
    out = []
    for i, w in enumerate(weeks):
        if i % every and i != n - 1:
            continue
        out.append(text(daylab(w), "%.2f" % sx(i), y, text_anchor="middle",
                        font_family="var(--mono)", font_size=12,
                        fill="var(--c-mute)"))
    return "".join(out)


def svg_open(vbw, vbh, title, desc, cls="chart__svg"):
    """Every chart carries role=img plus a title and desc naming the FINDING."""
    return ('<svg%s>%s%s' % (
        attrs(viewBox="0 0 %d %d" % (vbw, vbh), class_=cls, role="img",
              style="min-width:%dpx" % int(round(vbw * 0.86))),
        el("title", _h(title)), el("desc", _h(desc))))


def chart(vbw, vbh, title, desc, body):
    return htag("div", svg_open(vbw, vbh, title, desc) + body + "</svg>",
                class_="chart")


def tt(title, rows):
    """A tooltip payload. Rows are [label, value, colour-var or None].

    Serialised as JSON on the mark; the script inserts every string with
    textContent because analyst names, tower names and summaries come from Jira
    and are not trusted.
    """
    return json.dumps({"t": title, "r": rows}, separators=(",", ":"))


# ===========================================================================
# The style sheet
# ===========================================================================
#
# The first token block is byte-identical to demo.html's so the two files stay
# in sync; the --c-* / --s* / --o* chart tokens are appended.
#
# The categorical series set is VALIDATED at all pairs on both surfaces - see
# CONTROL-TOWER.md. Two measured constraints fall out of it and are honoured
# throughout this module:
#   * --s2 (#C25A17) and --sev-p1 (#A9322A) never share a plot area; measured
#     normal-vision dE 10.5, below the 15 floor. Panels 2/4/6 use --s2; panels
#     1/3/7 use the severity trio. No panel uses both.
#   * There is no fifth categorical hue. Six towers are a TABLE (panel 5); six
#     age bands are ORDINAL and use the single-hue teal ramp (panel 7).
#
# Note the :not([data-theme="light"]) guard on the media block. demo.html omits
# it, so a viewer forcing light theme on an OS-dark machine still gets dark
# tokens there. That bug is not copied forward.

CSS = """
:root {
  --ink:#0E1A1F; --ink-soft:#3B5057; --muted:#64787E; --rule:#C9D3D2;
  --paper:#EDF0EF; --raised:#F8FAF9; --accent:#0A6A70; --accent-dim:#0A6A7018;
  --sev-p1:#A9322A; --sev-warn:#96610C; --sev-ok:#276B50;

  --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --serif: Georgia, "Iowan Old Style", "Times New Roman", Times, serif;

  --fs-xs:0.71rem; --fs-sm:0.83rem; --fs-base:1.02rem;
  --fs-md:1.18rem; --fs-lg:1.5rem; --fs-xl:2.15rem; --fs-2xl:3.1rem;

  --c-surface:#F8FAF9; --c-grid:#DFE6E5; --c-axis:#C9D3D2;
  --c-ink:#3B5057; --c-mute:#64787E;

  --s1:#00929E; --s2:#C25A17; --s3:#6B5BD6; --s4:#9E2F62;
  --s1-wash:#00929E1A; --s2-wash:#C25A171A; --s3-wash:#6B5BD61A; --s4-wash:#9E2F621A;

  --o1:#6DBDC6; --o2:#43A9B3; --o3:#1B8D99; --o4:#09707C; --o5:#035059;

  --sev-warn-wash:#96610C14; --sev-p1-wash:#A9322A14; --sev-ok-wash:#276B5014;

  --sp-1:0.35rem; --sp-2:0.6rem; --sp-3:0.9rem;
  --sp-4:1.25rem; --sp-5:1.75rem; --sp-6:2.5rem; --sp-7:3.5rem;
  --measure:1180px;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ink:#E2EAE9; --ink-soft:#A8BCBF; --muted:#7D9296; --rule:#26363B;
    --paper:#0B1417; --raised:#131F23; --accent:#46BCC1; --accent-dim:#46BCC120;
    --sev-p1:#E0705F; --sev-warn:#D9A03C; --sev-ok:#5DB98C;
    --c-surface:#131F23; --c-grid:#1E2E33; --c-axis:#26363B;
    --c-ink:#A8BCBF; --c-mute:#7D9296;
    --s1:#12A2AC; --s2:#D2701F; --s3:#7B6FE0; --s4:#BE4478;
    --s1-wash:#12A2AC24; --s2-wash:#D2701F24; --s3-wash:#7B6FE024; --s4-wash:#BE447824;
    --o1:#0B5C66; --o2:#0E7A85; --o3:#12A2AC; --o4:#4FC0C8; --o5:#8ED6DC;
    --sev-warn-wash:#D9A03C1F; --sev-p1-wash:#E0705F1F; --sev-ok-wash:#5DB98C1F;
  }
}

:root[data-theme="dark"] {
  --ink:#E2EAE9; --ink-soft:#A8BCBF; --muted:#7D9296; --rule:#26363B;
  --paper:#0B1417; --raised:#131F23; --accent:#46BCC1; --accent-dim:#46BCC120;
  --sev-p1:#E0705F; --sev-warn:#D9A03C; --sev-ok:#5DB98C;
  --c-surface:#131F23; --c-grid:#1E2E33; --c-axis:#26363B;
  --c-ink:#A8BCBF; --c-mute:#7D9296;
  --s1:#12A2AC; --s2:#D2701F; --s3:#7B6FE0; --s4:#BE4478;
  --s1-wash:#12A2AC24; --s2-wash:#D2701F24; --s3-wash:#7B6FE024; --s4-wash:#BE447824;
  --o1:#0B5C66; --o2:#0E7A85; --o3:#12A2AC; --o4:#4FC0C8; --o5:#8ED6DC;
  --sev-warn-wash:#D9A03C1F; --sev-p1-wash:#E0705F1F; --sev-ok-wash:#5DB98C1F;
}

:root[data-theme="light"] {
  --ink:#0E1A1F; --ink-soft:#3B5057; --muted:#64787E; --rule:#C9D3D2;
  --paper:#EDF0EF; --raised:#F8FAF9; --accent:#0A6A70; --accent-dim:#0A6A7018;
  --sev-p1:#A9322A; --sev-warn:#96610C; --sev-ok:#276B50;
  --c-surface:#F8FAF9; --c-grid:#DFE6E5; --c-axis:#C9D3D2;
  --c-ink:#3B5057; --c-mute:#64787E;
  --s1:#00929E; --s2:#C25A17; --s3:#6B5BD6; --s4:#9E2F62;
  --s1-wash:#00929E1A; --s2-wash:#C25A171A; --s3-wash:#6B5BD61A; --s4-wash:#9E2F621A;
  --o1:#6DBDC6; --o2:#43A9B3; --o3:#1B8D99; --o4:#09707C; --o5:#035059;
  --sev-warn-wash:#96610C14; --sev-p1-wash:#A9322A14; --sev-ok-wash:#276B5014;
}

* { box-sizing: border-box; }

body {
  background: var(--paper); color: var(--ink);
  font-family: var(--sans); font-size: var(--fs-base); line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  margin: 0; padding: 0 var(--sp-4) var(--sp-7);
  overflow-x: hidden;
}
.shell { max-width: var(--measure); margin-inline: auto; }

.grid { display: grid; grid-template-columns: repeat(12, minmax(0,1fr));
        gap: var(--sp-4); align-items: start; }
.span-12 { grid-column: span 12; }
.span-8 { grid-column: span 8; }
.span-7 { grid-column: span 7; }
.span-6 { grid-column: span 6; }
.span-5 { grid-column: span 5; }
.span-4 { grid-column: span 4; }
@media (max-width: 1000px) {
  .span-8,.span-7,.span-6,.span-5,.span-4 { grid-column: span 12; }
}

/* ---- masthead ---- */
.mast { padding: var(--sp-6) 0 var(--sp-4); border-bottom: 2px solid var(--ink); }
.mast__eyebrow { font-family: var(--mono); font-size: var(--fs-xs);
  text-transform: uppercase; letter-spacing: 0.16em; color: var(--accent);
  font-weight: 600; }
.mast h1 { font-family: var(--serif); font-size: var(--fs-2xl); font-weight: 400;
  letter-spacing: -0.02em; line-height: 1.05; margin: var(--sp-2) 0 var(--sp-2); }
.mast__sub { color: var(--ink-soft); max-width: 68ch; margin: 0; }

.filters { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2);
  padding: var(--sp-3) 0 var(--sp-5); }
.filters__k { font-family: var(--mono); font-size: var(--fs-xs);
  text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); }
.chip { font-family: var(--mono); font-size: var(--fs-xs); cursor: default;
  border: 1px solid var(--rule); border-radius: 2px; padding: 0.25em 0.6em;
  color: var(--ink-soft); background: var(--raised);
  font-variant-numeric: tabular-nums; }
.chip--on { color: var(--accent); border-color: var(--accent);
  background: var(--accent-dim); font-weight: 650; }

/* ---- panels ---- */
.panel { background: var(--raised); border: 1px solid var(--rule);
  display: grid; grid-template-rows: auto 1fr auto; min-width: 0; }
.panel__hd { display: flex; flex-wrap: wrap; align-items: baseline;
  gap: var(--sp-2) var(--sp-3); padding: var(--sp-3) var(--sp-4);
  border-bottom: 1px solid var(--rule); }
.panel__eyebrow { font-family: var(--mono); font-size: var(--fs-xs);
  text-transform: uppercase; letter-spacing: 0.13em; color: var(--accent);
  font-weight: 600; }
.panel__title { font-family: var(--sans); font-size: var(--fs-md);
  font-weight: 650; letter-spacing: -0.005em; margin: 0; flex: 1 1 auto; }
.panel__tools { margin-left: auto; display: flex; gap: var(--sp-2); }
.panel__body { padding: var(--sp-4); min-width: 0; }
.panel__ft { padding: var(--sp-3) var(--sp-4); border-top: 1px solid var(--rule);
  font-size: var(--fs-sm); color: var(--ink-soft); }
.panel__ft strong { font-weight: 650; color: var(--ink); }
.panel__ft code { font-family: var(--mono); font-size: 0.92em; }

.tbtn { font-family: var(--mono); font-size: var(--fs-xs);
  text-transform: uppercase; letter-spacing: 0.1em; background: none;
  border: 1px solid var(--rule); color: var(--muted);
  padding: 0.22em 0.6em; border-radius: 2px; cursor: pointer; }
.tbtn:hover { color: var(--accent); border-color: var(--accent); }
.tbtn[aria-expanded="true"] { color: var(--accent); border-color: var(--accent);
  background: var(--accent-dim); }

.chart { overflow-x: auto; overflow-y: hidden; }
.chart > svg { display: block; height: auto; width: 100%; }

a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }

/* ---- scoreboard ---- */
.score { display: grid; gap: 1px; background: var(--rule);
  border-top: 1px solid var(--rule); border-bottom: 1px solid var(--rule);
  grid-template-columns: repeat(auto-fit, minmax(184px, 1fr)); }
.tile { background: var(--raised); padding: var(--sp-4) var(--sp-4) var(--sp-3);
  display: grid; gap: var(--sp-1); position: relative; align-content: start; }
.tile::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 3px;
  background: var(--tile-sev, transparent); }
.tile__k { font-family: var(--mono); font-size: var(--fs-xs);
  text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); }
.tile__v { font-size: var(--fs-xl); font-weight: 650; line-height: 1.05;
  letter-spacing: -0.02em; }
.tile__t { font-family: var(--mono); font-size: var(--fs-xs); color: var(--muted);
  font-variant-numeric: tabular-nums; }
.tile__st { display: inline-flex; align-items: center; gap: 0.35em;
  font-family: var(--mono); font-size: var(--fs-xs); font-weight: 600;
  letter-spacing: 0.06em; text-transform: uppercase; }
.tile__m { font-size: var(--fs-sm); color: var(--ink-soft); }
.tile--ok { --tile-sev: var(--sev-ok); }
.tile--warn { --tile-sev: var(--sev-warn); }
.tile--bad { --tile-sev: var(--sev-p1); }
.tile--ok .tile__st { color: var(--sev-ok); }
.tile--warn .tile__st { color: var(--sev-warn); }
.tile--bad .tile__st { color: var(--sev-p1); }
.tile__spark { margin-top: var(--sp-1); }

/* ---- tables ---- */
.tw { overflow-x: auto; }
table.t { border-collapse: collapse; width: 100%; font-size: var(--fs-sm); }
table.t thead th { font-family: var(--mono); font-size: var(--fs-xs);
  text-transform: uppercase; letter-spacing: 0.09em; color: var(--muted);
  font-weight: 600; text-align: left; padding: 0.5em 0.7em 0.5em 0;
  border-bottom: 1px solid var(--ink-soft); white-space: nowrap; }
table.t td { padding: 0.45em 0.7em 0.45em 0; border-bottom: 1px solid var(--rule);
  vertical-align: middle; }
table.t td.num, table.t th.num { text-align: right; font-family: var(--mono);
  font-variant-numeric: tabular-nums; white-space: nowrap; }
table.t tbody tr:hover { background: var(--accent-dim); }
table.t td.name { font-weight: 600; }
th[aria-sort] { cursor: pointer; user-select: none; }
th[aria-sort="descending"]::after { content: " \\25BE"; color: var(--accent); }
th[aria-sort="ascending"]::after { content: " \\25B4"; color: var(--accent); }
tr.rank1 { background: var(--accent-dim); }
.mbar { display: inline-block; vertical-align: middle; margin-left: 0.5em; }
.rank { font-family: var(--mono); font-weight: 700; font-size: var(--fs-xs);
  border: 1px solid var(--rule); border-radius: 2px; padding: 0.18em 0.5em;
  color: var(--muted); }
.rank--1 { color: var(--accent); border-color: var(--accent);
  background: var(--accent-dim); }
.twin { margin-top: var(--sp-4); border-top: 1px solid var(--rule);
  padding-top: var(--sp-3); }
.twin[hidden] { display: none; }

/* ---- legends & notes ---- */
.legend { display: flex; flex-wrap: wrap; gap: var(--sp-2) var(--sp-4);
  margin-top: var(--sp-3); font-size: var(--fs-sm); color: var(--ink-soft); }
.legend__i { display: inline-flex; align-items: center; gap: 0.45em; }
.legend__sw { width: 14px; height: 10px; border-radius: 2px; flex: 0 0 auto; }
.legend__ln { width: 16px; height: 2px; border-radius: 1px; flex: 0 0 auto; }
.legend__n { font-family: var(--mono); font-variant-numeric: tabular-nums;
  color: var(--muted); }
.note { font-size: var(--fs-sm); color: var(--ink-soft); margin: 0 0 var(--sp-3); }
.note--flag { color: var(--sev-warn); font-weight: 600; }
.kv { display: flex; flex-wrap: wrap; gap: var(--sp-1) var(--sp-4);
  font-family: var(--mono); font-size: var(--fs-xs); color: var(--muted);
  margin-top: var(--sp-3); font-variant-numeric: tabular-nums; }

/* ---- footer ---- */
.foot { margin-top: var(--sp-6); border-top: 2px solid var(--ink);
  padding-top: var(--sp-4); font-size: var(--fs-sm); color: var(--ink-soft); }
.foot h2 { font-family: var(--sans); font-size: var(--fs-md); font-weight: 650;
  margin: var(--sp-4) 0 var(--sp-2); color: var(--ink); }
.foot dl { display: grid; grid-template-columns: minmax(170px, auto) 1fr;
  gap: 0.3em var(--sp-4); margin: 0; }
.foot dt { font-family: var(--mono); font-size: var(--fs-xs); color: var(--accent);
  text-transform: uppercase; letter-spacing: 0.08em; padding-top: 0.25em; }
.foot dd { margin: 0; }
.foot code { font-family: var(--mono); font-size: 0.92em; }
.warnbox { border: 1px solid var(--sev-warn); background: var(--sev-warn-wash);
  padding: var(--sp-3) var(--sp-4); margin-top: var(--sp-4); font-size: var(--fs-sm); }
.warnbox b { color: var(--sev-warn); }
.okbox { border: 1px solid var(--rule); background: var(--sev-ok-wash);
  padding: var(--sp-3) var(--sp-4); margin-top: var(--sp-4); font-size: var(--fs-sm); }

/* ---- tooltip ---- */
.tt { position: fixed; z-index: 30; pointer-events: none; opacity: 0;
  background: var(--raised); border: 1px solid var(--rule);
  box-shadow: 0 2px 10px rgba(14,26,31,0.12);
  padding: var(--sp-2) var(--sp-3); font-size: var(--fs-sm);
  min-width: 148px; transition: opacity 90ms linear; }
.tt[data-on="1"] { opacity: 1; }
.tt__hd { font-family: var(--mono); font-size: var(--fs-xs); color: var(--muted);
  text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: var(--sp-1); }
.tt__row { display: flex; align-items: center; gap: 0.5em; }
.tt__key { width: 14px; height: 2px; border-radius: 1px; flex: 0 0 auto; }
.tt__n { color: var(--ink-soft); }
.tt__v { font-family: var(--mono); font-weight: 650; color: var(--ink);
  font-variant-numeric: tabular-nums; margin-left: auto; padding-left: 1em; }

.hit { cursor: default; }
.hit:hover .mark, .hit:focus .mark { filter: brightness(1.08); }
.cross { pointer-events: none; }

@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
@media (forced-colors: active), print {
  .seg--s2 { fill: url(#tx45); }
  .seg--s4 { fill: url(#tx135); }
}
@media print {
  body { background: #fff; }
  .panel { break-inside: avoid; }
  .tbtn { display: none; }
}
"""


# The one <defs> in the file: the two opt-in textures, on only under
# forced-colors or print, and only on the two panels with adjacent fills.
DEFS = ('<svg width="0" height="0" style="position:absolute" aria-hidden="true" '
        'focusable="false"><defs>'
        '<pattern id="tx45" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<rect width="6" height="6" fill="var(--s2)"/>'
        '<line x1="0" y1="0" x2="0" y2="6" stroke="var(--c-surface)" stroke-width="2"/>'
        '</pattern>'
        '<pattern id="tx135" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(135)">'
        '<rect width="6" height="6" fill="var(--s4)"/>'
        '<line x1="0" y1="0" x2="0" y2="6" stroke="var(--c-surface)" stroke-width="2"/>'
        '</pattern>'
        '</defs></svg>')


# ===========================================================================
# Panel scaffolding
# ===========================================================================

def panel(span, eyebrow, title, body, foot, table_id=None, table=None):
    tools = ""
    if table_id:
        tools = htag("div",
                     htag("button", "Table", class_="tbtn", type="button",
                          aria_expanded="false", aria_controls=table_id),
                     class_="panel__tools")
    hd = htag("div",
              htag("span", _h(eyebrow), class_="panel__eyebrow"),
              htag("h2", _h(title), class_="panel__title"),
              tools, class_="panel__hd")
    inner = body
    if table_id and table:
        inner += htag("div", table, class_="twin", id=table_id, hidden="hidden")
    return htag("section",
                hd,
                htag("div", inner, class_="panel__body"),
                htag("div", foot, class_="panel__ft"),
                class_="panel span-%d" % span)


def table_html(headers, rows, sortable=False, row_attrs=None):
    """headers: [(label, is_num)]. rows: [[cell_html, ...]] or [[(html, sortval)]]."""
    ths = []
    for i, (lab, isnum) in enumerate(headers):
        kw = {"class_": "num" if isnum else None}
        if sortable:
            kw["aria_sort"] = "none"
            kw["data_col"] = i
            kw["tabindex"] = "0"
            kw["role"] = "columnheader"
        ths.append(htag("th", _h(lab), **kw))
    body = []
    for ri, r in enumerate(rows):
        tds = []
        for i, cell in enumerate(r):
            val = None
            if isinstance(cell, tuple):
                cell, val = cell
            isnum = headers[i][1]
            tds.append(htag("td", cell,
                            class_="num" if isnum else ("name" if i == 0 else None),
                            data_v=None if val is None else "%s" % val))
        ra = (row_attrs or {}).get(ri, {})
        body.append(htag("tr", "".join(tds), **ra))
    return htag("div",
                htag("table",
                     htag("thead", htag("tr", "".join(ths))),
                     htag("tbody", "".join(body)),
                     class_="t"),
                class_="tw")


# ===========================================================================
# Panel 1 - the six-metric scoreboard
# ===========================================================================

# key, label, unit, higher-is-better, the sentence that says what it MEANS.
TILES = [
    ("ftr_pct", "First-time resolution (L1)", "pct", True,
     "Closed without ever reaching L2."),
    ("escalation_pct", "Escalation rate", "pct", False,
     "Reported work that ended up at L2."),
    ("reopen_pct", "Reopen rate", "pct", False,
     "Closed work that came back."),
    ("sla_pct", "Resolution SLA", "pct", True,
     "Of tickets adjudicated, share met."),
    ("response_pct", "Response SLA", "pct", True,
     "First human reply inside target."),
    ("aged_14d", "Aged backlog > 14d", "count", False,
     "Open now, reported over 14 days ago."),
]


def tile_state(tile, higher_better):
    """(css class, glyph, word). Colour is never the only channel.

    PASS -> on target. Otherwise within 10% relative of the target -> near.
    Otherwise below. The glyph inverts for a lower-is-better metric so an
    upward triangle always means "good", never merely "up".
    """
    target = tile.get("target")
    if target is None:
        return "", "–", "NO TARGET"
    v = float(tile["value"])
    t = float(target)
    if tile.get("verdict") == "PASS":
        return "tile--ok", ("▲" if higher_better else "▼"), "ON TARGET"
    near = abs(v - t) <= max(abs(t) * 0.10, 0.5)
    if near:
        return "tile--warn", "▬", "NEAR"
    return "tile--bad", ("▼" if higher_better else "▲"), "OFF TARGET"


def sparkline(pairs, target=None, vbw=168, vbh=40):
    """A trend, drawn from [(i, value or None)]. aria-hidden: the tile carries
    the current value and the table twin carries every point, so this mark is
    decoration-grade by construction.
    """
    vals = [v for _, v in pairs if v is not None]
    if len(vals) < 2:
        return ""
    p = 4
    n = max(len(pairs) - 1, 1)
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12 or (abs(hi) * 0.06 or 1.0)
    sx = linear(0, n, p, vbw - p)
    sy = linear(lo - pad, hi + pad, vbh - p, p)
    pts = [(sx(i), sy(v)) for i, v in pairs if v is not None]
    out = []
    for seg in runs([(sx(i), (sy(v) if v is not None else None))
                     for i, v in pairs]):
        if len(seg) > 1:
            out.append(el("path", d=area_d(seg, vbh - p), fill="var(--s1-wash)",
                          stroke="none"))
    if target is not None and (lo - pad) <= float(target) <= (hi + pad):
        out.append(el("line", x1=p, x2=vbw - p, y1="%.2f" % sy(target),
                      y2="%.2f" % sy(target), stroke="var(--c-axis)",
                      stroke_width=1, stroke_dasharray=None))
    for seg in runs([(sx(i), (sy(v) if v is not None else None))
                     for i, v in pairs]):
        if len(seg) > 1:
            out.append(el("path", d=polyline_d(seg), fill="none",
                          stroke="var(--s1)", stroke_width=2,
                          stroke_linejoin="round", stroke_linecap="round",
                          vector_effect="non-scaling-stroke"))
        else:
            out.append(el("circle", cx="%.2f" % seg[0][0], cy="%.2f" % seg[0][1],
                          r=2, fill="var(--s1)"))
    ex, ey = pts[-1]
    out.append(el("circle", cx="%.2f" % ex, cy="%.2f" % ey, r=5,
                  fill="var(--c-surface)"))
    out.append(el("circle", cx="%.2f" % ex, cy="%.2f" % ey, r=3.5, fill="var(--s1)"))
    return el("svg", "".join(out), viewBox="0 0 %d %d" % (vbw, vbh),
              width="100%", height="40", role="img", aria_hidden="true",
              focusable="false", preserveAspectRatio="none",
              class_="tile__spark")


def panel_scoreboard(m):
    weekly = m["weekly"]
    backlog = m["backlog"]
    sb = m["scoreboard"]

    tiles = []
    for key, label, unit, higher, meaning in TILES:
        t = sb[key]
        cls, glyph, word = tile_state(t, higher)
        if unit == "pct":
            value = pctlab(t["value"])
            series = [(i, w[key]) for i, w in enumerate(weekly)]
            sub = ratio(t["num"], t["den"])
        else:
            value = intlab(t["value"])
            series = [(i, b["aged"]) for i, b in enumerate(backlog)]
            sub = "%d open in total" % m["open"]
        tgt = t.get("target")
        tgt_txt = ("target %s%s (placeholder)"
                   % ((pctlab(tgt, 0) if unit == "pct" else intlab(tgt)),
                      "" if t.get("direction") is None
                      else (" or more" if t["direction"] == "ge" else " or less")))
        tiles.append(htag(
            "div",
            htag("span", _h(label), class_="tile__k"),
            htag("span", value, class_="tile__v"),
            htag("span", _h(sub), class_="tile__t"),
            htag("span", glyph + " " + word, class_="tile__st"),
            htag("span", _h(tgt_txt), class_="tile__t"),
            htag("span", _h(meaning), class_="tile__m"),
            sparkline(series, tgt),
            class_="tile " + cls))

    body = htag("div", "".join(tiles), class_="score")
    body += htag("p",
                 "Each sparkline is a weekly <strong>cohort</strong> rate: of the "
                 "tickets reported that week, how many ended up meeting SLA, "
                 "escalating or reopening. Weeks holding fewer than "
                 "%d tickets state no rate at all and the line breaks there - "
                 "the partial weeks at either end of any window are the most "
                 "eye-catching and least meaningful points on a chart. Aged "
                 "backlog is the exception: it is a <strong>stock</strong>, "
                 "reconstructed at each week boundary from the timeline, not a "
                 "flow counted inside a bucket." % A.MIN_WEEK_DENOM,
                 class_="note", style="margin-top:var(--sp-4)")

    # Table twin: all six metrics x all weeks.
    headers = [("Week reported", False), ("Volume", True), ("Closed", True),
               ("FTR %", True), ("Escalation %", True), ("Reopen %", True),
               ("Res. SLA %", True), ("Resp. SLA %", True)]
    rows = []
    for w in weekly:
        d = iso_to_date(w["week"])
        rows.append([_h(datelab(d)), intlab(w["n"]), intlab(w["closed"]),
                     pctlab(w["ftr_pct"]), pctlab(w["escalation_pct"]),
                     pctlab(w["reopen_pct"]), pctlab(w["sla_pct"]),
                     pctlab(w["response_pct"])])
    t1 = table_html(headers, rows)
    b_rows = [[_h("now" if b["week"] == "now" else datelab(iso_to_date(b["week"]))),
               intlab(b["open"]), intlab(b["aged"])] for b in backlog]
    t1 += htag("p", "Aged backlog, reconstructed at each week boundary:",
               class_="note", style="margin-top:var(--sp-4)")
    t1 += table_html([("Boundary", False), ("Open", True), ("Aged > 14d", True)],
                     b_rows)

    foot = ("Weekly buckets key off <strong>Reported At</strong>, never Jira's "
            "<code>created</code>. Every target on this row is a "
            "<strong>placeholder</strong> - invented, defensible, and to be "
            "replaced from a measured baseline. State is carried by a stripe, a "
            "glyph and a word, never by colour alone.")
    return panel(12, "Panel 1", "Scoreboard, with the trend behind each number",
                 body, foot, "t-1", t1)


# ===========================================================================
# Panel 2 - FTR against reopen, explicitly paired
# ===========================================================================

def panel_pairing(m):
    ser = m["ftr_vs_reopen"]
    if not ser:
        return ""
    weeks = [iso_to_date(p["week"]) for p in ser]
    n = len(ser)
    vbw, vbh = CHART_W[7], 300
    x0, x1 = PAD["l"], vbw - PAD["r"]
    band = (x1 - x0) / float(n)
    sx = linear(0, n - 1, x0 + band / 2.0, x1 - band / 2.0)

    # Pane A: first-time resolution. Pane B: reopen. Two panes, two baselines,
    # two independent scales, ONE x-axis. Never a dual-axis overlay: aligning
    # 0-100 against 0-9 on one frame invents a correlation out of arithmetic.
    a_top, a_base = 16.0, 170.0
    b_top, b_base = 194.0, 262.0

    fvals = [p["ftr_pct"] for p in ser if p["ftr_pct"] is not None] or [0.0]
    rvals = [p["reopen_pct"] for p in ser if p["reopen_pct"] is not None] or [0.0]
    at = ticks_for(min(fvals), max(fvals), 4, clamp_pct=True)
    bt = ticks_for(0.0, max(rvals), 3, clamp_pct=True)
    ay = linear(at[0], at[-1], a_base, a_top)
    by = linear(bt[0], bt[-1], b_base, b_top)

    parts = []

    # 1. Coupling bands, first so every mark sits above them.
    coupled = []
    for i in range(1, n):
        p, q = ser[i - 1], ser[i]
        if None in (p["ftr_pct"], q["ftr_pct"], p["reopen_pct"], q["reopen_pct"]):
            continue
        if (q["ftr_pct"] - p["ftr_pct"]) >= 2.0 and (q["reopen_pct"] - p["reopen_pct"]) >= 1.0:
            coupled.append(i)
    for i in coupled:
        parts.append(el("rect", x="%.2f" % (sx(i) - band / 2.0), y=a_top,
                        width="%.2f" % band, height="%.2f" % (b_base - a_top),
                        fill="var(--sev-warn-wash)", stroke="none"))
        parts.append(text("⚑ COUPLED", "%.2f" % sx(i), a_top - 4,
                          text_anchor="middle", font_family="var(--mono)",
                          font_size=10, font_weight=650, fill="var(--sev-warn)"))

    # 2. Frames.
    parts.append(gridlines(x0, x1, [(v, ay(v)) for v in at], lambda v: pctlab(v, 0)))
    parts.append(baseline(x0, x1, a_base))
    parts.append(gridlines(x0, x1, [(v, by(v)) for v in bt], lambda v: pctlab(v, 0)))
    parts.append(baseline(x0, x1, b_base))

    # 3. Series.
    for key, scale, tok, wash in (("ftr_pct", ay, "--s1", "--s1-wash"),
                                  ("reopen_pct", by, "--s2", "--s2-wash")):
        base = a_base if key == "ftr_pct" else b_base
        pairs = [(sx(i), (scale(p[key]) if p[key] is not None else None))
                 for i, p in enumerate(ser)]
        for seg in runs(pairs):
            if len(seg) > 1:
                parts.append(el("path", d=area_d(seg, base),
                                fill="var(%s)" % wash, stroke="none"))
        for seg in runs(pairs):
            if len(seg) > 1:
                parts.append(el("path", d=polyline_d(seg), fill="none",
                                stroke="var(%s)" % tok, stroke_width=2,
                                stroke_linejoin="round", stroke_linecap="round"))
            else:
                parts.append(el("circle", cx="%.2f" % seg[0][0],
                                cy="%.2f" % seg[0][1], r=2.5,
                                fill="var(%s)" % tok))
        last = [(i, p[key]) for i, p in enumerate(ser) if p[key] is not None]
        if last:
            li, lv = last[-1]
            ex, ey = sx(li), scale(lv)
            parts.append(el("circle", cx="%.2f" % ex, cy="%.2f" % ey, r=6,
                            fill="var(--c-surface)"))
            parts.append(el("circle", cx="%.2f" % ex, cy="%.2f" % ey, r=4,
                            fill="var(%s)" % tok))
            parts.append(text(pctlab(lv), "%.2f" % (ex - 8), "%.2f" % (ey - 8),
                              text_anchor="end", font_family="var(--mono)",
                              font_size=12, font_weight=650,
                              fill="var(%s)" % tok))

    # 4. Pane labels and the x axis.
    parts.append(text("FIRST-TIME RESOLUTION AT L1  %s–%s%%"
                      % (intlab(at[0]), intlab(at[-1])), x0, a_top - 4,
                      font_family="var(--mono)", font_size=10,
                      letter_spacing="0.08em", fill="var(--c-mute)"))
    parts.append(text("REOPEN RATE  %s–%s%%" % (intlab(bt[0]), intlab(bt[-1])),
                      x0, b_top - 4, font_family="var(--mono)", font_size=10,
                      letter_spacing="0.08em", fill="var(--c-mute)"))
    parts.append(week_ticks(weeks, sx, x1 - x0, 282))
    parts.append(text("week reported", "%.2f" % x1, 296, text_anchor="end",
                      font_family="var(--mono)", font_size=10,
                      fill="var(--c-mute)"))

    # 5. Crosshair + one hit band per week, spanning both panes. The hit target
    #    is the whole column; a 2px line is not a hit target.
    parts.append(el("line", class_="cross", x1=0, x2=0, y1=a_top, y2=b_base,
                    stroke="var(--c-axis)", stroke_width=1, opacity=0))
    for i, p in enumerate(ser):
        rows = [["First-time resolution", pctlab(p["ftr_pct"]), "--s1"],
                ["Reopen rate", pctlab(p["reopen_pct"]), "--s2"],
                ["Closed (shared denominator)", intlab(p["closed"]), None]]
        if i in coupled:
            rows.append(["Both moved the wrong way", "coupled", None])
        parts.append(el("rect", class_="hit", x="%.2f" % (sx(i) - band / 2.0),
                        y=a_top, width="%.2f" % band,
                        height="%.2f" % (b_base - a_top), fill="transparent",
                        tabindex="0", role="graphics-symbol",
                        data_x="%.2f" % sx(i),
                        aria_label="Week of %s: first-time resolution %s, reopen "
                                   "rate %s, over %d closed"
                                   % (datelab(weeks[i]), pctlab(p["ftr_pct"]),
                                      pctlab(p["reopen_pct"]), p["closed"]),
                        data_tt=tt("Week of " + datelab(weeks[i]), rows)))

    body = chart(vbw, vbh,
                 "First-time resolution against reopen rate, weekly",
                 "Two stacked panes on one shared week axis. Shaded weeks are "
                 "those where first-time resolution rose while reopen rate rose "
                 "with it.", "".join(parts))
    body += htag("div",
                 htag("span", el("span", class_="legend__ln",
                                 style="background:var(--s1)"),
                      "First-time resolution at L1", class_="legend__i"),
                 htag("span", el("span", class_="legend__ln",
                                 style="background:var(--s2)"),
                      "Reopen rate", class_="legend__i"),
                 htag("span", el("span", class_="legend__sw",
                                 style="background:var(--sev-warn-wash);"
                                       "border:1px solid var(--sev-warn)"),
                      "⚑ Both moved the wrong way together",
                      class_="legend__i"),
                 class_="legend")

    pr = m.get("pairing")
    if pr:
        body += htag("p",
                     "Across the %d weeks where both rates are stateable, "
                     "<strong>r = %.2f</strong>. With a dozen points that is "
                     "weak evidence and it is not offered as causation - the "
                     "argument here is structural, not empirical."
                     % (pr["weeks"], pr["r"]), class_="note",
                     style="margin-top:var(--sp-3)")

    rows = []
    for i, p in enumerate(ser):
        rows.append([_h(datelab(weeks[i])), intlab(p["closed"]),
                     pctlab(p["ftr_pct"]), pctlab(p["reopen_pct"]),
                     "coupled" if i in coupled else ""])
    t2 = table_html([("Week reported", False), ("Closed", True), ("FTR %", True),
                     ("Reopen %", True), ("Flag", False)], rows)

    foot = ("Closing early lifts the top line and wrecks the bottom one: both "
            "rates run over the <strong>same closed set</strong>, so a premature "
            "close moves a ticket into the FTR numerator this week and into the "
            "reopen numerator next week. Shaded weeks are where both moved the "
            "wrong way together - <strong>neither metric can be read alone</strong>. "
            "Two panes, two scales, two baselines; deliberately not a dual axis.")
    return panel(7, "Panel 2", "First-time resolution, paired with reopen",
                 body, foot, "t-2", t2)


# ===========================================================================
# Panel 3 - escalation rate per L1 analyst
# ===========================================================================

def panel_analysts(m):
    a = m["analysts"]
    people = a["people"]
    if not people:
        return ""
    vbw = CHART_W[5]
    gut, pitch, barh = 108, 26, 14
    top = 30
    vbh = top + len(people) * pitch + 34
    x0, x1 = gut, vbw - 28

    rates = [p["rate"] for p in people]
    tmax = max(rates + [a["hi"] or 0.0, a["pooled"]])
    ticks = ticks_for(0.0, tmax, 4, clamp_pct=True)
    sx = linear(ticks[0], ticks[-1], x0, x1)
    plot_bottom = top + len(people) * pitch

    parts = []

    # 1. The 2-sigma band, behind everything: the acceptable zone.
    if a["sd"] is not None:
        blo, bhi = max(0.0, a["lo"]), a["hi"]
        parts.append(el("rect", x="%.2f" % sx(blo), y=top - 6,
                        width="%.2f" % (sx(bhi) - sx(blo)),
                        height="%.2f" % (plot_bottom - top + 8),
                        fill="var(--accent-dim)", stroke="none"))
        parts.append(text("mean ± 2σ  %s–%s"
                          % (pctlab(blo, 0), pctlab(bhi, 0)),
                          "%.2f" % sx(blo), top - 12,
                          font_family="var(--mono)", font_size=10,
                          fill="var(--accent)"))

    # 2. Gridlines and baseline.
    for v in ticks:
        parts.append(el("line", x1="%.2f" % sx(v), y1=top - 6, x2="%.2f" % sx(v),
                        y2="%.2f" % plot_bottom, stroke="var(--c-grid)",
                        stroke_width=1))
        parts.append(text(pctlab(v, 0), "%.2f" % sx(v), plot_bottom + 16,
                          text_anchor="middle", font_family="var(--mono)",
                          font_size=12, fill="var(--c-mute)"))
    parts.append(el("line", x1=x0, y1=top - 6, x2=x0, y2="%.2f" % plot_bottom,
                    stroke="var(--c-axis)", stroke_width=1))

    # 3. The pooled mean line - the same numerator over the same denominator as
    #    the tower headline, so the two reconcile by construction.
    mx = sx(a["mean"])
    parts.append(el("line", x1="%.2f" % mx, y1=top - 6, x2="%.2f" % mx,
                    y2="%.2f" % plot_bottom, stroke="var(--c-ink)",
                    stroke_width=1))
    flip = mx > (x0 + x1) / 2.0
    parts.append(text("mean %s" % pctlab(a["mean"]),
                      "%.2f" % (mx + (-4 if flip else 4)), plot_bottom + 30,
                      text_anchor="end" if flip else "start",
                      font_family="var(--mono)", font_size=11,
                      fill="var(--c-ink)"))

    # 4. Bars.
    for i, p in enumerate(people):
        y = top + i * pitch
        by = y + (pitch - barh) / 2.0
        out = bool(p.get("outlier"))
        thin = not p.get("rateable")
        tok = "--sev-warn" if out else ("--c-mute" if thin else "--s1")
        w = sx(p["rate"]) - x0
        rows = [["Escalation rate", pctlab(p["rate"]), tok],
                ["Escalated / handled",
                 ratio(p["escalated"], p["handled"]), None]]
        if p.get("sigma") is not None:
            rows.append(["Sigma from tower mean", "%+.2f" % p["sigma"], None])
        if thin:
            rows.append(["Below n=%d" % a["floor"], "not rated", None])
        label = ("%s, escalation rate %s, %d of %d tickets%s"
                 % (p["analyst"], pctlab(p["rate"]), p["escalated"],
                    p["handled"],
                    ", outside 2 sigma" if out else
                    (", below the rating floor" if thin else "")))
        marks = [hrect(x0, by, w, barh, 4, fill="var(%s)" % tok, class_="mark")]
        # Name: weight is the third channel on an outlier, after hue and chip.
        marks.append(text(p["analyst"], gut - 8, y + pitch / 2.0 + 4,
                          text_anchor="end", font_family="var(--sans)",
                          font_size=12,
                          font_weight=650 if out else 400,
                          fill="var(--c-mute)" if thin else "var(--c-ink)"))
        vx = x0 + w + 6
        marks.append(text(pctlab(p["rate"]), "%.2f" % vx, y + pitch / 2.0 + 4,
                          font_family="var(--mono)", font_size=11,
                          fill="var(--c-ink)"))
        if out:
            marks.append(text("▲ 2σ", "%.2f" % (vx + 40),
                              y + pitch / 2.0 + 4, font_family="var(--mono)",
                              font_size=10, font_weight=650,
                              fill="var(--sev-warn)"))
        marks.append(text("n=%d" % p["handled"], vbw - 4, y + pitch / 2.0 + 4,
                          text_anchor="end", font_family="var(--mono)",
                          font_size=10, fill="var(--c-mute)"))
        marks.append(el("rect", x=0, y="%.2f" % y, width=vbw,
                        height=pitch, fill="transparent"))
        parts.append(el("g", "".join(marks), class_="hit", tabindex="0",
                        role="graphics-symbol", aria_label=label,
                        data_tt=tt(p["analyst"], rows)))

    body = chart(vbw, vbh, "Escalation rate by L1 analyst",
                 "Horizontal bars sorted high to low, with the tower mean and a "
                 "two-sigma band. %d of %d rated analysts fall outside the band."
                 % (len(a["outliers"]), a["rated"]), "".join(parts))

    if a["criterion_6"] == "met":
        verdict_html = htag(
            "div", "<b>PILOT.md exit criterion 6: met.</b> %d rated analysts, "
            "<strong>0 outside 2σ</strong>. The band is %s to %s "
            "(mean %s, σ %s)."
            % (a["rated"], pctlab(max(0.0, a["lo"])), pctlab(a["hi"]),
               pctlab(a["mean"]), f1(a["sd"])), class_="okbox")
    elif a["criterion_6"] == "gap":
        verdict_html = htag(
            "div", "<b>PILOT.md exit criterion 6: gap.</b> %d of %d rated "
            "analysts sit outside 2σ &mdash; %s."
            % (len(a["outliers"]), a["rated"],
               _h(", ".join(a["outliers"]))), class_="warnbox")
    else:
        verdict_html = htag(
            "div", "<b>Criterion 6 not judged.</b> Fewer than three analysts "
            "clear the n=%d floor, so no band can be computed. Suppressed rather "
            "than guessed." % a["floor"], class_="warnbox")
    body += verdict_html

    rows = []
    for p in people:
        rows.append([_h(p["analyst"]), intlab(p["handled"]),
                     intlab(p["escalated"]), pctlab(p["rate"]),
                     "" if p.get("sigma") is None else "%+.2f" % p["sigma"],
                     "" if p.get("z") is None else "%+.2f" % p["z"],
                     "outside 2σ" if p.get("outlier")
                     else ("not rated (n < %d)" % a["floor"]
                           if not p.get("rateable") else "")])
    t3 = table_html([("L1 analyst", False), ("Handled", True),
                     ("Escalated", True), ("Rate %", True), ("Sigma", True),
                     ("z vs pooled", True), ("Note", False)], rows)

    foot = ("PILOT.md exit criterion 6 &mdash; <strong>no analyst diverges more "
            "than 2σ from the tower mean</strong>. Band is mean ± 2σ "
            "across analysts with n ≥ %d; analysts below that floor are "
            "plotted in grey and excluded from σ, because one new starter's "
            "first three tickets would otherwise double the standard deviation "
            "and widen the band until no real outlier could ever be detected. "
            "Keyed on the <strong>L1 Analyst field</strong>, never the Jira "
            "assignee &mdash; on escalation the assignee moves to L2, which would "
            "credit the escalation to whoever received it."
            % a["floor"])
    return panel(5, "Panel 3", "Escalation rate per L1 analyst", body, foot,
                 "t-3", t3)


# ===========================================================================
# Panel 4 - the KB gap
# ===========================================================================

def panel_kb(m):
    kb = m["kb"]
    ser = kb["series"]
    if not ser:
        return ""
    weeks = [iso_to_date(p["week"]) for p in ser]
    n = len(ser)
    vbw, vbh = CHART_W[7], 300
    x0, x1 = PAD["l"], vbw - PAD["r"]
    band = (x1 - x0) / float(n)
    sx = linear(0, n - 1, x0 + band / 2.0, x1 - band / 2.0)

    a_top, a_base = 16.0, 170.0
    b_top, b_base = 194.0, 262.0

    cmax = max([p["escalated"] for p in ser] + [1])
    ct = ticks_for(0, cmax, 4)
    ay = linear(ct[0], ct[-1], a_base, a_top)
    bt = ticks_for(0.0, max([p["gap_pct"] or 0.0 for p in ser] + [kb["pct"]]),
                   3, clamp_pct=True)
    by = linear(bt[0], bt[-1], b_base, b_top)

    parts = [gridlines(x0, x1, [(v, ay(v)) for v in ct], intlab),
             baseline(x0, x1, a_base),
             gridlines(x0, x1, [(v, by(v)) for v in bt], lambda v: pctlab(v, 0)),
             baseline(x0, x1, b_base)]

    # Pane A: stacked columns. Applied below, gap above - the segment that
    # matters sits at the top where its length is read against the cap.
    colw = min(24.0, band * 0.62)
    gap_max_i = max(range(n), key=lambda i: ser[i]["gap"])
    for i, p in enumerate(ser):
        cx = sx(i)
        applied = p["escalated"] - p["gap"]
        y_esc = ay(p["escalated"])
        y_app = ay(applied)
        marks = []
        if applied > 0:
            # Square top: it meets the 2px surface gap, not a data end.
            marks.append(el("rect", x="%.2f" % (cx - colw / 2.0),
                            y="%.2f" % y_app, width="%.2f" % colw,
                            height="%.2f" % max(0.0, a_base - y_app),
                            fill="var(--o2)", class_="mark"))
        if p["gap"] > 0:
            h = max(0.0, y_app - y_esc - 2.0)   # the 2px surface gap
            marks.append(rrect(cx - colw / 2.0, y_esc, colw, h, 4,
                               fill="var(--s2)", class_="mark seg--s2"))
        if i in (gap_max_i, n - 1) and p["gap"] > 0:
            marks.append(text(intlab(p["gap"]), "%.2f" % cx,
                              "%.2f" % (y_esc - 6), text_anchor="middle",
                              font_family="var(--mono)", font_size=12,
                              font_weight=650, fill="var(--s2)"))
        marks.append(el("rect", x="%.2f" % (cx - band / 2.0), y=a_top,
                        width="%.2f" % band,
                        height="%.2f" % (b_base - a_top), fill="transparent"))
        rows = [["No article found", intlab(p["gap"]), "--s2"],
                ["Article applied", intlab(applied), "--o2"],
                ["Escalations", intlab(p["escalated"]), None],
                ["Share with no article", pctlab(p["gap_pct"]), None]]
        parts.append(el("g", "".join(marks), class_="hit", tabindex="0",
                        role="graphics-symbol", data_x="%.2f" % cx,
                        aria_label="Week of %s: %d of %d escalations found no KB "
                                   "article" % (datelab(weeks[i]), p["gap"],
                                                p["escalated"]),
                        data_tt=tt("Week of " + datelab(weeks[i]), rows)))

    # Pane B: the share, as a line that breaks where the week is too thin.
    pairs = [(sx(i), (by(p["gap_pct"]) if p["gap_pct"] is not None else None))
             for i, p in enumerate(ser)]
    for seg in runs(pairs):
        if len(seg) > 1:
            parts.append(el("path", d=area_d(seg, b_base), fill="var(--s2-wash)",
                            stroke="none"))
    mean_y = by(kb["pct"])
    parts.append(el("line", x1=x0, x2=x1, y1="%.2f" % mean_y, y2="%.2f" % mean_y,
                    stroke="var(--c-axis)", stroke_width=1))
    parts.append(text("%d-day mean %s" % (m["window_days"], pctlab(kb["pct"], 0)),
                      "%.2f" % (x1 - 2), "%.2f" % (mean_y - 5),
                      text_anchor="end", font_family="var(--mono)",
                      font_size=10, fill="var(--c-mute)"))
    for seg in runs(pairs):
        if len(seg) > 1:
            parts.append(el("path", d=polyline_d(seg), fill="none",
                            stroke="var(--s2)", stroke_width=2,
                            stroke_linejoin="round", stroke_linecap="round"))
        else:
            parts.append(el("circle", cx="%.2f" % seg[0][0], cy="%.2f" % seg[0][1],
                            r=2.5, fill="var(--s2)"))
    stated = [(i, p["gap_pct"]) for i, p in enumerate(ser)
              if p["gap_pct"] is not None]
    if stated:
        li, lv = stated[-1]
        parts.append(el("circle", cx="%.2f" % sx(li), cy="%.2f" % by(lv), r=6,
                        fill="var(--c-surface)"))
        parts.append(el("circle", cx="%.2f" % sx(li), cy="%.2f" % by(lv), r=4,
                        fill="var(--s2)"))
        parts.append(text(pctlab(lv, 0), "%.2f" % (sx(li) - 8),
                          "%.2f" % (by(lv) - 8), text_anchor="end",
                          font_family="var(--mono)", font_size=12,
                          font_weight=650, fill="var(--s2)"))

    parts.append(text("ESCALATIONS PER WEEK  0–%s" % intlab(ct[-1]),
                      x0, a_top - 4, font_family="var(--mono)", font_size=10,
                      letter_spacing="0.08em", fill="var(--c-mute)"))
    parts.append(text("SHARE FINDING NO ARTICLE  %s–%s%%"
                      % (intlab(bt[0]), intlab(bt[-1])), x0, b_top - 4,
                      font_family="var(--mono)", font_size=10,
                      letter_spacing="0.08em", fill="var(--c-mute)"))
    parts.append(week_ticks(weeks, sx, x1 - x0, 282))
    parts.append(el("line", class_="cross", x1=0, x2=0, y1=a_top, y2=b_base,
                    stroke="var(--c-axis)", stroke_width=1, opacity=0))

    body = chart(vbw, vbh, "Escalations that found no knowledge-base article",
                 "Weekly escalations split into those with an article applied "
                 "and those that found none, with the share below.",
                 "".join(parts))
    body += htag("div",
                 htag("span", el("span", class_="legend__sw",
                                 style="background:var(--s2)"),
                      "No article found", class_="legend__i"),
                 htag("span", el("span", class_="legend__sw",
                                 style="background:var(--o2)"),
                      "Article applied", class_="legend__i"),
                 class_="legend")

    # The actionable output: which articles to write next.
    by_tower = kb["by_tower"][:6]
    by_reason = kb["by_reason"][:6]
    if by_tower:
        body += htag("p", "<strong>The backlog, in the order it should be "
                     "written.</strong> By tower: " +
                     _h(", ".join("%s %d" % (t, c) for t, c in by_tower)) +
                     ". By escalation reason: " +
                     _h(", ".join("%s %d" % (t, c) for t, c in by_reason)) + ".",
                     class_="note", style="margin-top:var(--sp-3)")

    rows = []
    for i, p in enumerate(ser):
        rows.append([_h(datelab(weeks[i])), intlab(p["escalated"]),
                     intlab(p["escalated"] - p["gap"]), intlab(p["gap"]),
                     pctlab(p["gap_pct"])])
    t4 = table_html([("Week reported", False), ("Escalations", True),
                     ("Article applied", True), ("No article", True),
                     ("Gap %", True)], rows)

    foot = ("<strong>%d of %d escalations (%s) found no KB article.</strong> "
            "Each one is a ticket that reached L2 because knowledge was missing, "
            "not because expertise was required &mdash; the largest single lever "
            "in the design. Counted on the KB field alone, on the exact option "
            "<code>%s</code>: <code>No</code> means <em>not checked</em>, which "
            "is a process failure rather than a content gap, and conflating the "
            "two would overstate this backlog. The weekly share breaks where the "
            "week holds fewer than %d escalations; the count never abstains."
            % (kb["gap"], kb["escalated"], pctlab(kb["pct"]),
               _h(A.KB_NONE_FOUND), A.MIN_WEEK_DENOM))
    return panel(7, "Panel 4", "The knowledge gap behind the escalations",
                 body, foot, "t-4", t4)


# ===========================================================================
# Panel 5 - tower comparison and the pilot ranking
# ===========================================================================

def mbar(value, vmax, width=56, height=8):
    """A micro-bar. ONE colour for every row: a value ramp over nominal
    categories double-encodes length as hue and is an anti-pattern."""
    w = 0.0 if vmax <= 0 else max(0.0, float(value)) / float(vmax) * width
    return el("svg",
              el("rect", x=0, y=0, width=width, height=height, rx=2,
                 fill="var(--rule)"),
              hrect(0, 0, w, height, 2, fill="var(--s1)"),
              viewBox="0 0 %d %d" % (width, height), width=width, height=height,
              class_="mbar", aria_hidden="true", focusable="false")


def panel_towers(m):
    towers = m["towers"]
    if not towers:
        return ""
    esc_min = min(t["escalation_pct"] for t in towers)
    for t in towers:
        t["headroom"] = t["escalation_pct"] - esc_min

    vmax = max(t["volume"] for t in towers) or 1
    fmax = max(t["ftr_pct"] for t in towers) or 1.0
    emax = max(t["escalation_pct"] for t in towers) or 1.0
    smax = max(t["sla_pct"] for t in towers) or 1.0
    amax = max(t["aged"] for t in towers) or 1
    hmax = max(t["headroom"] for t in towers) or 1.0

    headers = [("Tower", False), ("Volume", True), ("FTR %", True),
               ("Escalation %", True), ("Res. SLA %", True), ("Aged > 14d", True),
               ("Headroom pp", True), ("Pilot rank", True)]
    rows, rattrs = [], {}
    for i, t in enumerate(sorted(towers, key=lambda x: x["pilot_rank"])):
        rank1 = t["pilot_rank"] == 1
        if rank1:
            rattrs[i] = {"class_": "rank1"}
        rows.append([
            (_h(t["tower"]), t["tower"]),
            (intlab(t["volume"]) + mbar(t["volume"], vmax), t["volume"]),
            (pctlab(t["ftr_pct"]) + mbar(t["ftr_pct"], fmax), "%.4f" % t["ftr_pct"]),
            (pctlab(t["escalation_pct"]) + mbar(t["escalation_pct"], emax),
             "%.4f" % t["escalation_pct"]),
            (pctlab(t["sla_pct"]) + mbar(t["sla_pct"], smax), "%.4f" % t["sla_pct"]),
            (intlab(t["aged"]) + mbar(t["aged"], amax), t["aged"]),
            (f1(t["headroom"]) + mbar(t["headroom"], hmax), "%.4f" % t["headroom"]),
            (htag("span", intlab(t["pilot_rank"]),
                  class_="rank rank--1" if rank1 else "rank"), t["pilot_rank"]),
        ])
    body = table_html(headers, rows, sortable=True, row_attrs=rattrs)

    top = sorted(towers, key=lambda x: x["pilot_rank"])[0]
    body += htag("p",
                 "<strong>Recommended pilot tower: %s.</strong> %d tickets in "
                 "window, first-time resolution %s, escalation %s &mdash; big "
                 "enough for a result to be visible and weak enough to have room "
                 "to move. Sorting the table re-orders the rows; it never "
                 "re-colours anything, so an entity keeps its identity."
                 % (_h(top["tower"]), top["volume"], pctlab(top["ftr_pct"]),
                    pctlab(top["escalation_pct"])),
                 class_="note", style="margin-top:var(--sp-3)")

    foot = ("Ranked by <strong>volume × (100 − FTR%)</strong> &mdash; "
            "volume enough for the result to be significant, first-time "
            "resolution weak enough to have headroom. <em>Headroom pp</em> is a "
            "tower's escalation rate minus the lowest rate any tower achieves: "
            "the tickets a pilot could plausibly move. Not a quality judgement, "
            "and not a league table. <strong>Aged</strong> is a project-wide "
            "snapshot, deliberately not windowed &mdash; a 30-day window would "
            "hide the oldest tickets, which are the ones that matter.")
    return panel(5, "Panel 5", "Tower comparison, and where to pilot",
                 body, foot)


# ===========================================================================
# Panel 6 - intake mix, with chat surfaced
# ===========================================================================

def panel_intake(m):
    mix = [c for c in m["intake"] if c["n"] > 0]
    if not mix:
        return ""
    total = sum(c["n"] for c in mix) or 1
    vbw = CHART_W[6]
    x0, x1 = 8, vbw - 8
    bar_y, bar_h = 14, 28
    vbh = 62
    # Slot order is domain.INTAKE_CHANNELS order, never rank order, so a
    # regeneration never repaints the chart.
    slots = ["--s1", "--s2", "--s3", "--s4"]
    parts = []
    cx = float(x0)
    span = float(x1 - x0)
    for i, c in enumerate(mix):
        tok = slots[i % len(slots)]
        w = span * c["n"] / float(total)
        wg = max(0.0, w - (2.0 if i < len(mix) - 1 else 0.0))  # 2px surface gap
        first, last = i == 0, i == len(mix) - 1
        # Rounded only on the two OUTER ends of the whole bar; every internal
        # join stays square, so the 2px surface gap reads as a seam rather than
        # as four separate pills.
        cls = "mark"
        if tok == "--s2":
            cls = "mark seg--s2"
        elif tok == "--s4":
            cls = "mark seg--s4"
        if first and last:
            shape = el("rect", x="%.2f" % cx, y=bar_y, width="%.2f" % wg,
                       height=bar_h, rx=4, fill="var(%s)" % tok, class_=cls)
        elif first:
            shape = lrect(cx, bar_y, wg, bar_h, 4, fill="var(%s)" % tok, class_=cls)
        elif last:
            shape = hrect(cx, bar_y, wg, bar_h, 4, fill="var(%s)" % tok, class_=cls)
        else:
            shape = el("rect", x="%.2f" % cx, y=bar_y, width="%.2f" % wg,
                       height=bar_h, fill="var(%s)" % tok, class_=cls)
        marks = [shape]
        lab = "%s %s" % (c["channel"], pctlab(c["pct"], 0))
        if wg > len(lab) * 6.6 + 16:
            marks.append(text(lab, "%.2f" % (cx + wg / 2.0), bar_y + bar_h / 2.0 + 4,
                              text_anchor="middle", font_family="var(--mono)",
                              font_size=12, fill="var(--c-surface)"))
        marks.append(el("rect", x="%.2f" % cx, y=0, width="%.2f" % max(w, 1.0),
                        height=vbh, fill="transparent"))
        parts.append(el("g", "".join(marks), class_="hit", tabindex="0",
                        role="graphics-symbol",
                        aria_label="%s: %d tickets, %s of intake"
                                   % (c["channel"], c["n"], pctlab(c["pct"])),
                        data_tt=tt(c["channel"],
                                   [["Tickets", intlab(c["n"]), tok],
                                    ["Share of intake", pctlab(c["pct"]), None]])))
    parts.append(text("share of %d tickets reported in window" % total, x0, 58,
                      font_family="var(--mono)", font_size=10,
                      fill="var(--c-mute)"))

    body = chart(vbw, vbh, "Intake mix by channel",
                 "One hundred percent stacked bar, four channels in model order.",
                 "".join(parts))

    leg = []
    for i, c in enumerate(mix):
        tok = slots[i % len(slots)]
        leg.append(htag("span",
                        el("span", class_="legend__sw",
                           style="background:var(%s)" % tok),
                        _h(c["channel"]),
                        htag("span", "%d · %s" % (c["n"], pctlab(c["pct"], 1)),
                             class_="legend__n"),
                        class_="legend__i"))
    body += htag("div", "".join(leg), class_="legend")

    # Chat only, trended. It is the only channel whose count means something
    # beyond volume: those tickets did not previously exist as tickets at all.
    chat_ser = m.get("chat_weekly") or []
    if chat_ser:
        cw, ch = CHART_W[6], 96
        cx0, cx1 = PAD["l"], cw - PAD["r"]
        n = len(chat_ser)
        cband = (cx1 - cx0) / float(n)
        csx = linear(0, n - 1, cx0 + cband / 2.0, cx1 - cband / 2.0)
        cmax = max([p["n"] for p in chat_ser] + [1])
        cticks = ticks_for(0, cmax, 2)
        csy = linear(cticks[0], cticks[-1], 62, 12)
        cp = [gridlines(cx0, cx1, [(v, csy(v)) for v in cticks], intlab),
              baseline(cx0, cx1, 62)]
        pts = [(csx(i), csy(p["n"])) for i, p in enumerate(chat_ser)]
        cp.append(el("path", d=area_d(pts, 62), fill="var(--s4-wash)", stroke="none"))
        cp.append(el("path", d=polyline_d(pts), fill="none", stroke="var(--s4)",
                     stroke_width=2, stroke_linejoin="round",
                     stroke_linecap="round"))
        ex, ey = pts[-1]
        cp.append(el("circle", cx="%.2f" % ex, cy="%.2f" % ey, r=6,
                     fill="var(--c-surface)"))
        cp.append(el("circle", cx="%.2f" % ex, cy="%.2f" % ey, r=4,
                     fill="var(--s4)"))
        cp.append(text(intlab(chat_ser[-1]["n"]), "%.2f" % (ex - 8),
                       "%.2f" % (ey - 8), text_anchor="end",
                       font_family="var(--mono)", font_size=12, font_weight=650,
                       fill="var(--s4)"))
        cp.append(text("CHAT TICKETS PER WEEK", cx0, 10,
                       font_family="var(--mono)", font_size=10,
                       letter_spacing="0.08em", fill="var(--c-mute)"))
        cp.append(week_ticks([iso_to_date(p["week"]) for p in chat_ser],
                             csx, cx1 - cx0, 80))
        for i, p in enumerate(chat_ser):
            cp.append(el("rect", class_="hit", x="%.2f" % (csx(i) - cband / 2.0),
                         y=8, width="%.2f" % cband, height=58, fill="transparent",
                         tabindex="0", role="graphics-symbol",
                         aria_label="Week of %s: %d chat tickets"
                                    % (datelab(iso_to_date(p["week"])), p["n"]),
                         data_tt=tt("Chat · week of "
                                    + datelab(iso_to_date(p["week"])),
                                    [["Tickets", intlab(p["n"]), "--s4"]])))
        body += chart(cw, ch, "Chat intake per week",
                      "The chat channel alone, trended weekly.", "".join(cp))

    q = {c["channel"]: c for c in m.get("channel_quality", [])}
    rows = []
    for c in mix:
        qq = q.get(c["channel"], {})
        rows.append([_h(c["channel"]), intlab(c["n"]), pctlab(c["pct"]),
                     pctlab(qq.get("ftr_pct")) if qq else "",
                     pctlab(qq.get("escalation_pct")) if qq else ""])
    t6 = table_html([("Channel", False), ("Tickets", True), ("Share %", True),
                     ("FTR %", True), ("Escalation %", True)], rows)

    chat = next((c for c in mix if c["shadow"]), None)
    chat_n = chat["n"] if chat else 0
    chat_q = q.get("Chat", {})
    quality = ""
    if chat_q and chat_q.get("n"):
        quality = (" Those tickets resolve first time %s of the time against a "
                   "tower average of %s, so the claim is measurable rather than "
                   "rhetorical."
                   % (pctlab(chat_q["ftr_pct"]),
                      pctlab(m["scoreboard"]["ftr_pct"]["value"])))
    foot = ("<strong>Chat is shadow support pulled into the record.</strong> %d "
            "tickets that in most towers would have been a direct message to an "
            "engineer &mdash; uncounted, unplanned, outside every SLA.%s Channels "
            "are drawn in model order, never in rank order, so the eye can find "
            "chat in the same place every time the file is regenerated."
            % (chat_n, quality))
    return panel(6, "Panel 6", "Where the work arrives from", body, foot,
                 "t-6", t6)


# ===========================================================================
# Panel 7 - ageing distribution of open work
# ===========================================================================

def panel_ageing(m):
    ag = m["ageing"]
    raw = ag["buckets"]
    if not raw:
        return ""

    # analytics carries six half-open buckets; the ordinal ramp has five steps
    # and a duplicated step would break the ordering the ramp exists to encode.
    # The last two are therefore collapsed for the CHART - which preserves the
    # sum exactly - while the table twin below lists all six unmodified.
    if len(raw) == 6:
        tail = {"label": "30d+", "lo": raw[4]["lo"], "hi": None,
                "n": raw[4]["n"] + raw[5]["n"], "breach": True}
        cells = raw[:4] + [tail]
    else:
        cells = raw

    vbw, vbh = CHART_W[6], 240
    x0, x1 = PAD["l"], vbw - PAD["r"]
    top, base = 52.0, vbh - PAD["b"]
    n = len(cells)
    band = (x1 - x0) / float(n)
    colw = min(24.0, band - 2.0)                 # the 2px surface gap
    ticks = ticks_for(0, max([c["n"] for c in cells] + [1]), 4)
    sy = linear(ticks[0], ticks[-1], base, top)
    ramp = ["--o1", "--o2", "--o3", "--o4", "--o5"]

    parts = [gridlines(x0, x1, [(v, sy(v)) for v in ticks], intlab),
             baseline(x0, x1, base)]
    total = ag["total"] or 1
    for i, c in enumerate(cells):
        cx = x0 + band * (i + 0.5)
        y = sy(c["n"])
        tok = ramp[min(i, len(ramp) - 1)]
        marks = [rrect(cx - colw / 2.0, y, colw, base - y, 4,
                       fill="var(%s)" % tok, class_="mark")]
        marks.append(text(intlab(c["n"]), "%.2f" % cx, "%.2f" % (y - 7),
                          text_anchor="middle", font_family="var(--mono)",
                          font_size=12, fill="var(--c-ink)"))
        marks.append(text(c["label"], "%.2f" % cx, base + 18, text_anchor="middle",
                          font_family="var(--mono)", font_size=12,
                          fill="var(--c-mute)"))
        marks.append(el("rect", x="%.2f" % (cx - band / 2.0), y=top - 20,
                        width="%.2f" % band, height="%.2f" % (base - top + 20),
                        fill="transparent"))
        parts.append(el("g", "".join(marks), class_="hit", tabindex="0",
                        role="graphics-symbol",
                        aria_label="%s old: %d open tickets, %s of open work"
                                   % (c["label"], c["n"],
                                      pctlab(100.0 * c["n"] / total)),
                        data_tt=tt(c["label"] + " old",
                                   [["Open tickets", intlab(c["n"]), tok],
                                    ["Share of open work",
                                     pctlab(100.0 * c["n"] / total), None]])))

    # The bracket is the finding; the distribution's shape is unremarkable.
    breach = [i for i, c in enumerate(cells) if c["breach"]]
    if breach:
        bx0 = x0 + band * breach[0] + (band - colw) / 2.0 - 2
        bx1 = x0 + band * (breach[-1] + 1) - (band - colw) / 2.0 + 2
        byy = 34.0
        parts.append(el("path",
                        d="M %.2f %.2f L %.2f %.2f L %.2f %.2f L %.2f %.2f"
                          % (bx0, byy + 6, bx0, byy, bx1, byy, bx1, byy + 6),
                        fill="none", stroke="var(--sev-warn)", stroke_width=1))
        parts.append(text("⚑ aged backlog · %d tickets"
                          % sum(c["n"] for c in cells if c["breach"]),
                          "%.2f" % ((bx0 + bx1) / 2.0), byy - 6,
                          text_anchor="middle", font_family="var(--mono)",
                          font_size=11, font_weight=650, fill="var(--sev-warn)"))
    parts.append(text("OPEN TICKETS BY AGE", x0, 14, font_family="var(--mono)",
                      font_size=10, letter_spacing="0.08em", fill="var(--c-mute)"))

    body = chart(vbw, vbh, "Age distribution of open work",
                 "Five ordered age bands over %d open tickets, with the aged "
                 "backlog bracketed." % ag["total"], "".join(parts))

    st = m.get("ageing_by_status") or {}
    if st:
        body += htag("p",
                     "Of the %d open tickets, <strong>%d are the tower's own "
                     "queue</strong> and %d sit in %s &mdash; waiting on someone "
                     "else, with the SLA clock legitimately paused. Without that "
                     "split this panel would accuse the tower of work it is not "
                     "currently holding. Median age %s days; oldest %s days."
                     % (ag["total"], st.get("owned_total", 0),
                        st.get("paused_total", 0),
                        _h(" or ".join(D.SLA_PAUSED_STATUSES)),
                        f1(ag["median"]), f1(ag["oldest"])),
                     class_="note", style="margin-top:var(--sp-3)")

    rows = []
    by_lab = {c["label"]: c for c in (st.get("buckets") or [])}
    for c in raw:
        s = by_lab.get(c["label"], {})
        rows.append([_h(c["label"]), intlab(c["n"]),
                     pctlab(100.0 * c["n"] / total),
                     intlab(s.get("owned", 0)) if s else "",
                     intlab(s.get("paused", 0)) if s else "",
                     "aged" if c["breach"] else ""])
    t7 = table_html([("Age band", False), ("Open", True), ("Share %", True),
                     ("Tower-held", True), ("Paused", True), ("Flag", False)],
                    rows)

    foot = ("Point-in-time at <strong>%s</strong>, over open work across the "
            "whole project rather than the window &mdash; an %s-day-old ticket "
            "is exactly what this panel is for, and windowing would hide it. "
            "Open means <code>statusCategory != Done</code>; age runs from "
            "<strong>Reported At</strong>. Bands are half-open so they partition "
            "the open set exactly. The chart collapses the last two analytics "
            "bands into <code>30d+</code> to keep the ordinal ramp strictly "
            "ordered; the table above lists all %d unmodified."
            % (_h(m["generated_label"]), f1(ag["oldest"]), len(raw)))
    return panel(6, "Panel 7", "How old the open work is", body, foot, "t-7", t7)


# ===========================================================================
# Masthead, provenance and footer
# ===========================================================================

def masthead(m):
    head = htag(
        "header",
        htag("div", "Control tower · %s" % _h(m["project"]),
             class_="mast__eyebrow"),
        htag("h1", "The numbers Jira cannot draw"),
        htag("p",
             "Six metrics, trended on a custom datetime field Jira stores no "
             "history for; an escalation rate normalised per analyst and judged "
             "against a dispersion band; and two metrics paired so that gaming "
             "one exposes the other. Every figure below was computed from a "
             "<strong>single read</strong> of %s and carries its own denominator."
             % _h(m["project"]),
             class_="mast__sub"),
        class_="mast")

    chips = [
        htag("span", "Window", class_="filters__k"),
        htag("span", "%d days · %s" % (m["window_days"], _h(m["window_label"])),
             class_="chip chip--on"),
        htag("span", "Project", class_="filters__k"),
        htag("span", _h(m["project"]), class_="chip chip--on"),
        htag("span", "Read", class_="filters__k"),
        htag("span", "%s · %d issues · %d requests · one fetch"
             % (_h(m["generated_label"]), m["total_issues"], m["pages"]),
             class_="chip"),
        htag("button", "Theme", class_="tbtn", type="button", id="theme",
             title="Cycle auto / light / dark"),
    ]
    return head + htag("div", "".join(chips), class_="filters")


def footer(m):
    inv = m["invariants"]
    sums = m["weekly_sums"]
    warns = m["warnings"]

    boxes = ""
    if sums:
        boxes += htag("div", "<b>Bucket check failed.</b> " +
                      _h("; ".join(sums)) +
                      " The trend panels are not trustworthy in this state: a row "
                      "outside the axis vanishes from every sparkline while still "
                      "counting in the headline.", class_="warnbox")
    else:
        boxes += htag("div", "<b>Bucket check passed.</b> The weekly buckets "
                      "partition the window exactly &mdash; weekly volume sums to "
                      "the %d issues in window, and the paired and KB panels "
                      "reconcile to the same closed and escalated sets."
                      % m["volume"], class_="okbox")
    if inv:
        boxes += htag("div", "<b>Invariants: %d condition(s) reported.</b><br>"
                      % len(inv) + "<br>".join(_h(i) for i in inv) +
                      "<br><br>These are data conditions, not rendering faults. "
                      "They are printed rather than masked because a panel whose "
                      "invariant has failed is not slightly off &mdash; it is "
                      "asserting something the data no longer supports.",
                      class_="warnbox")
    else:
        boxes += htag("div", "<b>Invariants: all hold.</b> Resolved At agrees "
                      "with statusCategory on every row, so the backlog "
                      "reconstruction is sound; the KB gap numerator is a subset "
                      "of the escalation denominator; the age bands partition the "
                      "open set; and every issue carries a Reported At.",
                      class_="okbox")
    if warns:
        boxes += htag("div", "<b>Schema warnings from the read.</b><br>" +
                      "<br>".join(_h(w) for w in warns), class_="warnbox")

    jt = m["jira_time_counterexample"]
    dl = [
        ("Time axis",
         "Every bucket, trend and age on this page keys off the <strong>Reported "
         "At</strong> custom field. Jira's own <code>created</code> holds %d "
         "distinct date(s) across all %d issues and <code>resolutiondate</code> "
         "holds %d, because both are read-only over REST and were stamped at "
         "seed time. Using either would collapse every trend on this page into a "
         "single column. That is the whole reason this file exists rather than a "
         "dashboard gadget."
         % (jt["created_distinct_dates"], m["total_issues"],
            jt["resolutiondate_distinct_dates"])),
        ("Data strategy",
         "One paginated read of <code>/rest/api/3/search/jql</code> (%d requests, "
         "%d issues), then every panel computed in memory as a pure function. The "
         "alternative &mdash; one JQL count per metric per week per tower &mdash; "
         "is several hundred round-trips that rate-limit, and its totals would "
         "not even reconcile with each other because each count is evaluated at a "
         "different instant." % (m["pages"], m["total_issues"])),
        ("Targets",
         "Every target on this page is a <strong>PLACEHOLDER</strong> (CLAIMS.md "
         "#14/#15): invented, defensible, and to be replaced from a measured "
         "baseline. They are drawn as a thin reference line, never as a benchmark, "
         "and no tile claims to pass an agreed standard."),
        ("First-time resolution",
         "Closed in window and never left L1, over closed work excluding "
         "Problems &mdash; a Problem is an investigation by definition and "
         "counting it would punish doing the right thing. %s."
         % _h(ratio(m["scoreboard"]["ftr_pct"]["num"],
                    m["scoreboard"]["ftr_pct"]["den"]))),
        ("Escalation rate",
         "Support Tier at L2, over <em>every</em> issue reported in window, "
         "Problems included. The denominators of FTR and escalation deliberately "
         "differ, and both mirror the JQL in <code>app/metrics.py</code> exactly, "
         "quirks included, so the page and the CLI baseline cannot disagree on "
         "stage."),
        ("Reopen rate",
         "Reopened = Yes among issues reported in window, over the closed set. "
         "The numerator ranges over the window while the denominator is the "
         "closed subset; that asymmetry is inherited from the reference "
         "implementation rather than silently improved on here."),
        ("SLA attainment",
         "Met / (Met + Breached). Tickets with no verdict are outside the "
         "denominator entirely, which is why the resolution denominator (%d) is "
         "not the closed count (%d)."
         % (m["scoreboard"]["sla_pct"]["den"], m["closed"])),
        ("Aged backlog",
         "A <strong>stock</strong>, not a flow: at each week boundary, issues "
         "reported by then, not yet resolved by then, and older than %d days. "
         "Reconstructed from the timeline because Jira keeps no history of the "
         "field it depends on." % A.AGED_DAYS),
        ("Weekly floor",
         "A week with fewer than %d tickets states no rate; the line breaks. On "
         "this window the edge weeks would otherwise read 0%% and 100%% &mdash; "
         "the two most eye-catching points on the chart, and both pure noise."
         % A.MIN_WEEK_DENOM),
        ("Analyst floor",
         "An analyst with fewer than %d tickets is plotted but excluded from the "
         "mean and σ. Including them lets one new starter's first three "
         "tickets double the standard deviation, widening the band until the "
         "criterion passes for the wrong reason." % A.MIN_ANALYST_N),
        ("Accessibility",
         "Every chart has a table twin holding the exact numbers it draws, "
         "reachable from the panel header &mdash; no value on this page is "
         "available only on hover. Marks are keyboard reachable. State is carried "
         "by stripe, glyph and word as well as hue. The page renders completely "
         "with JavaScript disabled."),
        ("Provenance",
         "Generated %s from project %s at %s. Self-contained: no network, no CDN, "
         "no web font, no analytics. This file can be mailed as an attachment and "
         "opened offline."
         % (_h(m["generated_label"]), _h(m["project"]), _h(m["site"] or "n/a"))),
    ]
    dts = "".join(htag("dt", _h(k)) + htag("dd", v) for k, v in dl)

    return htag("footer",
                htag("h2", "How to read this, and what to distrust"),
                boxes,
                htag("h2", "Method"),
                htag("dl", dts),
                class_="foot")


# ===========================================================================
# Script - the only JS in the file
# ===========================================================================
#
# It computes no coordinate and holds no data. Everything it touches is already
# rendered and correct without it: it adds the theme cycle, the table-twin
# disclosure, column sorting, and a tooltip. All strings are inserted with
# textContent because analyst names, tower names and summaries come from Jira.

SCRIPT = """
(function () {
  "use strict";
  var root = document.documentElement;

  // ---- theme: auto -> light -> dark -------------------------------------
  var btn = document.getElementById("theme");
  function store(v) { try { v ? localStorage.setItem("ct-theme", v)
                              : localStorage.removeItem("ct-theme"); }
                      catch (e) {} }
  try { var saved = localStorage.getItem("ct-theme");
        if (saved) root.setAttribute("data-theme", saved); } catch (e) {}
  if (btn) btn.addEventListener("click", function () {
    var cur = root.getAttribute("data-theme");
    var next = cur === "light" ? "dark" : (cur === "dark" ? null : "light");
    if (next) { root.setAttribute("data-theme", next); }
    else { root.removeAttribute("data-theme"); }
    store(next);
    btn.setAttribute("title", "Theme: " + (next || "auto"));
  });

  // ---- table twins -------------------------------------------------------
  Array.prototype.forEach.call(
    document.querySelectorAll(".tbtn[aria-controls]"), function (b) {
      b.addEventListener("click", function () {
        var t = document.getElementById(b.getAttribute("aria-controls"));
        if (!t) return;
        var open = b.getAttribute("aria-expanded") === "true";
        b.setAttribute("aria-expanded", open ? "false" : "true");
        if (open) { t.setAttribute("hidden", "hidden"); }
        else { t.removeAttribute("hidden"); }
      });
    });

  // ---- sortable table (panel 5) -----------------------------------------
  Array.prototype.forEach.call(
    document.querySelectorAll("th[aria-sort]"), function (th) {
      function sort() {
        var table = th.closest("table");
        var tbody = table.tBodies[0];
        var col = +th.getAttribute("data-col");
        var dir = th.getAttribute("aria-sort") === "descending"
                  ? "ascending" : "descending";
        Array.prototype.forEach.call(
          table.querySelectorAll("th[aria-sort]"), function (o) {
            o.setAttribute("aria-sort", "none");
          });
        th.setAttribute("aria-sort", dir);
        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function (a, b) {
          var x = a.cells[col].getAttribute("data-v");
          var y = b.cells[col].getAttribute("data-v");
          var nx = parseFloat(x), ny = parseFloat(y);
          var c;
          if (!isNaN(nx) && !isNaN(ny)) { c = nx - ny; }
          else { c = String(x).localeCompare(String(y)); }
          return dir === "ascending" ? c : -c;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      }
      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
      });
    });

  // ---- tooltip -----------------------------------------------------------
  var tip = document.createElement("div");
  tip.className = "tt";
  tip.setAttribute("role", "status");
  document.body.appendChild(tip);

  function hide() {
    tip.setAttribute("data-on", "0");
    Array.prototype.forEach.call(document.querySelectorAll(".cross"),
      function (c) { c.setAttribute("opacity", "0"); });
  }

  function fill(payload) {
    while (tip.firstChild) { tip.removeChild(tip.firstChild); }
    var hd = document.createElement("div");
    hd.className = "tt__hd";
    hd.textContent = payload.t;
    tip.appendChild(hd);
    (payload.r || []).forEach(function (r) {
      var row = document.createElement("div");
      row.className = "tt__row";
      var key = document.createElement("span");
      key.className = "tt__key";
      key.style.background = r[2] ? "var(" + r[2] + ")" : "transparent";
      var name = document.createElement("span");
      name.className = "tt__n";
      name.textContent = r[0];
      var val = document.createElement("span");
      val.className = "tt__v";
      val.textContent = r[1];
      row.appendChild(key); row.appendChild(name); row.appendChild(val);
      tip.appendChild(row);
    });
  }

  function place(x, y) {
    var w = tip.offsetWidth, h = tip.offsetHeight;
    var left = Math.min(Math.max(8, x + 14), window.innerWidth - w - 8);
    var top = Math.min(Math.max(8, y + 14), window.innerHeight - h - 8);
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }

  function show(el, x, y) {
    var raw = el.getAttribute("data-tt");
    if (!raw) return;
    var payload;
    try { payload = JSON.parse(raw); } catch (e) { return; }
    fill(payload);
    tip.setAttribute("data-on", "1");
    place(x, y);
    var svg = el.ownerSVGElement || el.closest("svg");
    var cross = svg && svg.querySelector(".cross");
    var cx = el.getAttribute("data-x");
    if (cross && cx) {
      cross.setAttribute("x1", cx);
      cross.setAttribute("x2", cx);
      cross.setAttribute("opacity", "1");
    }
  }

  Array.prototype.forEach.call(document.querySelectorAll(".hit"), function (el) {
    el.addEventListener("pointermove", function (e) { show(el, e.clientX, e.clientY); });
    el.addEventListener("pointerenter", function (e) { show(el, e.clientX, e.clientY); });
    el.addEventListener("pointerleave", hide);
    el.addEventListener("focus", function () {
      var r = el.getBoundingClientRect();
      show(el, r.left + r.width / 2, r.top + r.height / 2);
    });
    el.addEventListener("blur", hide);
  });
  window.addEventListener("scroll", hide, true);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") hide();
  });
})();
"""


# ===========================================================================
# The page
# ===========================================================================

def render(model):
    """model -> a complete HTML document. Pure: no IO, no Jira, no clock."""
    m = model
    panels = [
        panel_scoreboard(m),
        panel_pairing(m),
        panel_analysts(m),
        panel_kb(m),
        panel_towers(m),
        panel_intake(m),
        panel_ageing(m),
    ]
    title = "Control tower · %s · %s" % (m["project"], m["window_label"])
    doc = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="color-scheme" content="light dark">',
        "<title>%s</title>" % _h(title),
        "<style>%s</style>" % CSS,
        "</head>",
        "<body>",
        DEFS,
        '<div class="shell">',
        masthead(m),
        '<div class="grid">',
        "".join(panels),
        "</div>",
        footer(m),
        "</div>",
        "<script>%s</script>" % SCRIPT,
        "</body>",
        "</html>",
        "",
    ]
    return NL.join(doc)


# ===========================================================================
# Model
# ===========================================================================

def chat_weekly(rows, now, days, channel="Chat"):
    """Weekly count for one intake channel. A COUNT, so it never abstains -
    MIN_WEEK_DENOM governs rates, and this is not a rate."""
    axis, buckets = A.bucket_weeks(rows, now, days)
    return [{"week": w.isoformat(),
             "n": sum(1 for r in buckets[w] if r.intake == channel)}
            for w in axis]


def build_model(rows, now, days, project, site="", pages=0, warnings=()):
    """Everything the page needs, from a list of store.Issue records.

    Pure. No Jira handle, no filesystem, no wall clock - `now` is supplied - so
    the whole page is reproducible from a frozen snapshot.
    """
    m = A.compute_all(rows, now, days)
    m["project"] = project
    m["site"] = site
    m["pages"] = pages
    m["warnings"] = list(warnings)
    m["chat_weekly"] = chat_weekly(rows, now, days)

    tz = A.data_tz(rows) or now.tzinfo
    local = now.astimezone(tz) if tz else now
    m["generated_label"] = "%s %02d:%02d %s" % (
        datelab(local.date()), local.hour, local.minute,
        local.strftime("%Z") or "UTC")

    weekly = m["weekly"]
    if weekly:
        first = iso_to_date(weekly[0]["week"])
        m["window_label"] = "%s – %s" % (daylab(first), datelab(local.date()))
    else:
        m["window_label"] = "%d days to %s" % (days, datelab(local.date()))
    return m


# ===========================================================================
# CLI
# ===========================================================================

def add_arguments(ap):
    # The project key is an ARGUMENT, not a constant, for the same reason it is
    # one in app/metrics.py: this has to run against OPS, ITSM or a fresh
    # instance without knowing which one it is.
    ap.add_argument("--project", default=os.environ.get("JIRA_PROJECT"),
                    help="Jira project key, e.g. OPS or ITSM (or set JIRA_PROJECT)")
    ap.add_argument("--days", type=int, default=90,
                    help="trend window in days, measured on Reported At (default 90)")
    ap.add_argument("--out", type=str, default="out/control-tower.html",
                    help="output path (default out/control-tower.html)")
    ap.add_argument("--json", type=str,
                    help="also write the computed model as JSON, for testing")
    return ap


def run(args):
    if not args.project:
        raise SystemExit("--project is required (or set JIRA_PROJECT)")

    require_env()
    j = Jira()

    # Resolve the schema by NAME first. Against an instance missing a field,
    # every panel that depends on it would otherwise render confident zeroes -
    # a page that looks merely disappointing rather than broken.
    F = FIELDS.resolve(j)
    for w in F.warnings():
        warn("  ! " + w)

    log("Reading %s once ..." % args.project)
    st = S.fetch(j, args.project, F)
    log("  %d issues in %d request(s)." % (len(st), st.pages))
    for w in st.warnings:
        warn("  ! " + w)

    model = build_model(st.issues, st.now, args.days, args.project,
                        site=st.site, pages=st.pages, warnings=st.warnings)

    for bad in model["weekly_sums"]:
        warn("  ! bucket check: " + bad)
    for bad in model["invariants"]:
        warn("  ! invariant: " + bad)

    html = render(model)
    out = Path(args.out)
    if out.parent and str(out.parent) not in ("", "."):
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    log("")
    log("  %-22s %s" % ("project", args.project))
    log("  %-22s %d days (%s)" % ("window", args.days, model["window_label"]))
    log("  %-22s %d in window / %d total"
        % ("issues", model["volume"], model["total_issues"]))
    log("  %-22s %s  %s" % ("first-time resolution",
                            pctlab(model["scoreboard"]["ftr_pct"]["value"]),
                            ratio(model["scoreboard"]["ftr_pct"]["num"],
                                  model["scoreboard"]["ftr_pct"]["den"])))
    log("  %-22s %s" % ("escalation rate",
                        pctlab(model["scoreboard"]["escalation_pct"]["value"])))
    log("  %-22s %d of %d (%s)" % ("kb gap", model["kb"]["gap"],
                                   model["kb"]["escalated"],
                                   pctlab(model["kb"]["pct"])))
    log("  %-22s %s" % ("criterion 6", model["analysts"]["criterion_6"] or "n/a"))
    log("")
    log("written to %s (%.0f KB)" % (out, out.stat().st_size / 1024.0))

    if args.json:
        Path(args.json).write_text(json.dumps(model, indent=2, default=str),
                                   encoding="utf-8")
        log("model written to %s" % args.json)


def main(argv=None):
    ap = add_arguments(argparse.ArgumentParser(prog="app.cli tower"))
    run(ap.parse_args(argv))


if __name__ == "__main__":
    main()
