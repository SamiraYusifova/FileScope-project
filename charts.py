# charts.py - builds the two Altair charts (age histogram and income x age scatter).

import altair as alt
import numpy as np
import pandas as pd

ORANGE = "#EE6A2B"
GREY = "#DAD6CC"
PALE_YELLOW = "#FFF3C4"
DOT_GREY = "#A9A59C"
BLACK = "#111111"
AGE_SCALE = alt.Scale(domain=[16, 92], nice=False)  # both charts show ages 16-92


def is_in_brush(age, brush):
    """True when an age is inside the brush, e.g. 30 is inside (25, 44)."""
    return brush is not None and brush[0] <= age <= brush[1]


# ---------- Step 6: histogram ----------


def style_chart(chart):
    """White background, light grid and small mono labels, to match the page style."""
    return (
        chart.configure(background="#FFFFFF")
        .configure_view(stroke=None)
        .configure_axis(
            labelFont="JetBrains Mono",
            titleFont="JetBrains Mono",
            labelColor="#6B675F",
            titleColor="#6B675F",
            labelFontSize=10,
            titleFontSize=10,
            gridColor="#ECE8DE",
            domainColor=BLACK,
        )
    )


def histogram_chart(bins, brush):
    """Bar chart of people per 4-year age group, with a draggable brush on the x axis."""
    bins = bins.copy()
    bins["bin_end"] = bins["bin_start"] + 4
    # A bar is orange when the middle of its age group is inside the brush.
    bins["inside"] = [is_in_brush(start + 1.5, brush) for start in bins["bin_start"]]

    # The brush: drag left/right to select ages. It starts at the current brush.
    # The brush box is drawn as a dashed outline.
    look = alt.BrushConfig(fill=PALE_YELLOW, fillOpacity=0.35, stroke=BLACK, strokeDash=[4, 3])
    if brush:
        selection = alt.selection_interval(
            name="brush", encodings=["x"], mark=look, value={"x": list(brush)}
        )
    else:
        selection = alt.selection_interval(name="brush", encodings=["x"], mark=look)

    chart = (
        alt.Chart(bins, height=220)
        .mark_bar(stroke=BLACK, strokeWidth=1)
        .encode(
            x=alt.X("bin_start:Q", title="Age", scale=AGE_SCALE),
            x2="bin_end:Q",
            y=alt.Y("people:Q", title=None),
            y2=alt.datum(0),
            color=alt.Color(
                "inside:N",
                scale=alt.Scale(domain=[True, False], range=[ORANGE, GREY]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("bin_start:Q", title="From age"),
                alt.Tooltip("people:Q", title="People", format=","),
            ],
        )
        .add_params(selection)
    )
    return style_chart(chart)


def read_brush(chart_state, current_brush, last_seen):
    """Works out the brush from what the chart reported.

    Returns (new_brush, new_last_seen). The chart reports a range like [24.6, 44.2]
    after a drag, and nothing after the brush is cleared. We only react when that
    report changes, so re-drawing the chart never resets the brush by accident.
    """
    if chart_state is None:
        return current_brush, last_seen
    reported = chart_state.selection.get("brush", {}).get("bin_start")
    reported = tuple(reported) if reported else None
    if reported == last_seen:
        return current_brush, last_seen
    if reported is None:
        return None, None
    return (round(reported[0]), round(reported[1])), reported


# ---------- Step 7: scatter plot ----------


def scatter_chart(points, brush):
    """Dots for income vs age. Dots inside the brush are orange, the band is pale yellow."""
    points = points.copy()
    points["inside"] = [is_in_brush(age, brush) for age in points["age"]]
    # Ages are whole numbers, so dots would line up in columns. Spread them a little
    # (only for drawing). The fixed seed keeps the dots in the same place every time.
    spread = np.random.default_rng(seed=7).uniform(-0.4, 0.4, len(points))
    points["age_drawn"] = points["age"] + spread
    # A few people earn a lot; stop the y axis at the 97th percentile so the rest is readable.
    top = float(points["income"].quantile(0.97)) if len(points) else 1

    dots = (
        alt.Chart(points)
        .mark_circle(size=14, opacity=0.9)
        .encode(
            x=alt.X("age_drawn:Q", title="Age", scale=AGE_SCALE),
            y=alt.Y("income:Q", title="Income", scale=alt.Scale(domain=[0, top], clamp=True),
                    axis=alt.Axis(format="$~s")),
            color=alt.Color(
                "inside:N",
                scale=alt.Scale(domain=[True, False], range=[ORANGE, DOT_GREY]),
                legend=None,
            ),
            order=alt.Order("inside:N"),  # orange dots are drawn on top
            tooltip=["age:Q", alt.Tooltip("income:Q", format="$,")],
        )
    )
    if not brush:
        return style_chart(dots.properties(height=220))

    band = pd.DataFrame({"low": [brush[0]], "high": [brush[1]]})
    shade = (
        alt.Chart(band)
        .mark_rect(color=PALE_YELLOW)
        .encode(x=alt.X("low:Q", scale=AGE_SCALE), x2="high:Q")
    )
    return style_chart((shade + dots).properties(height=220))