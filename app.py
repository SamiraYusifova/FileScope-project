import html 
from pathlib import Path
import duckdb
import streamlit as st
import charts
import data

st.set_page_config(page_title="FileScope", page_icon="FS", layout="wide")
css = (Path(__file__).parent / "style.css").read_text(encoding="utf-8")
st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

def show(html_text):
    st.markdown(html_text,unsafe_allow_html=True)

@st.cache_resource
def get_connection():
    return data.create_database()

connection=get_connection()
db=connection.cursor()
state=st.session_state

defaults={"table":None, "sql_text":"", "base_sql":None,"total_rows":0,"query_ms":None,
            "error": None, "history":[],"page": 1,"brush":(25,44),"brush_seen":None}
for key,value in defaults.items():
    state.setdefault(key,value)

def run_sql(sql):
    """Runs the SQL. If it works, it becomes the base query."""
    sql = data.clean_sql(sql)
    try:
        state.total_rows, state.query_ms = data.count_rows(db, sql)
    except duckdb.Error as error:
        state.error = str(error)  # show the error, keep the old results
        return
    state.base_sql = sql
    state.error = None
    state.page = 1
    state.history = ([sql] + [old for old in state.history if old != sql])[:20]


def open_query(sql):
    """Puts a query in the SQL box and runs it (used by HISTORY and UPLOAD)."""
    state.sql_text = sql
    run_sql(sql)

if state.table:
    row_count, column_count = data.describe_table(db, state.table)
    name, meta = state.table, f"{row_count:,} rows · {column_count} cols"
else:
    name, meta = "no data yet", "upload a file to start"

with st.container(border=True, key="card_header"):
    title_col, history_col, upload_col, export_col = st.columns([6, 1, 1, 1.2], vertical_alignment="center")
    with title_col:
        show(
            f'<div class="header"><span class="logo">F</span><span class="brand">FILESCOPE</span>'
            f'<span class="crumb">Datasets / <b>{name}</b></span><span class="meta">{meta}</span></div>'
        )

    with history_col.popover("History", width="stretch"):  # click a query to run it again
        if not state.history:
            st.caption("No queries yet.")
        for index, old_sql in enumerate(state.history):
            st.button(old_sql, key=f"history_{index}", on_click=open_query, args=(old_sql,))

    with upload_col.popover("Upload", width="stretch"):
        file = st.file_uploader("CSV or Parquet file", type=["csv", "parquet"])
        if file and file.file_id != state.get("loaded_file_id"):  # load each file only once
            state.loaded_file_id = file.file_id
            try:
                state.table = data.load_uploaded_file(db, file)
            except duckdb.Error as error:
                st.error(f"Could not load {file.name}: {error}")
            else:
                st.cache_data.clear()  # forget results from the previous file
                open_query(f'SELECT * FROM "{state.table}"')
                st.rerun()

    current_sql = state.base_sql  # the CSV is only built when the button is clicked
    export_col.download_button("Export CSV", data=lambda: data.export_csv(connection.cursor(), current_sql),
                               file_name=f"{name}_export.csv", width="stretch", disabled=current_sql is None)

if state.base_sql is None:  # nothing to explore yet: show a welcome box and stop here
    with st.container(border=True, key="card_welcome"):
        show('<div class="card-title">Start here</div>')
        st.markdown("Click **UPLOAD** and choose a CSV or Parquet file. "
                    "The charts need columns named `age` and `income`.")
    st.stop()
# ===== 4. SQL BAR =====

with st.form("sql_form", border=False), st.container(border=True, key="card_sql"):
    label_col, editor_col, run_col = st.columns([0.6, 9, 1.4], vertical_alignment="center")
    with label_col:
        show('<div class="sql-label">SQL</div>')
    editor_col.text_area("SQL", key="sql_text", height=80, label_visibility="collapsed")
    if run_col.form_submit_button("Run ⌘↵", type="primary", width="stretch"):  # or Ctrl/Cmd+Enter
        run_sql(state.sql_text)
        st.rerun()
    with run_col:
        show(f'<div class="meta right">{state.query_ms:.0f} ms</div>')

if state.error:
    message = html.escape(state.error).replace("\n", "<br>")  # safe text that keeps line breaks
    show(f'<div class="sql-error">{message}</div>')

base_sql = state.base_sql


# ===== 5. CHARTS =====

# Read the brush dragged on the histogram (Streamlit keeps it under the chart's key "age_chart").
state.brush, state.brush_seen = charts.read_brush(state.get("age_chart"), state.brush, state.brush_seen)
brush = state.brush
left, right = st.columns(2)

with left.container(border=True, key="card_histogram"):
    if brush:
        tag = f'<span class="tag yellow">Brush {brush[0]}–{brush[1]}</span>'
    else:
        tag = '<span class="meta">Drag to select ages</span>'
    show(f'<div class="card-title">Age distribution {tag}</div>')
    try:
        chart = charts.histogram_chart(data.histogram(db, base_sql), brush)
        st.altair_chart(chart, key="age_chart", on_select="rerun", theme=None, width="stretch")
    except duckdb.Error:
        st.info("This chart needs an `age` column.")

with right.container(border=True, key="card_scatter"):
    show('<div class="card-title">Income × Age <span class="tag blue">Linked</span></div>')
    try:
        chart = charts.scatter_chart(data.scatter_sample(db, base_sql), brush)
        st.altair_chart(chart, theme=None, width="stretch")
    except duckdb.Error:
        st.info("This chart needs `age` and `income` columns.")

brush_count = None
if brush:
    try:
        brush_count = data.count_in_brush(db, base_sql, brush[0], brush[1])
    except duckdb.Error:
        pass


# ===== 6. RESULTS TABLE =====

total = state.total_rows
page_count = max(1, (total + data.PAGE_SIZE - 1) // data.PAGE_SIZE)

with st.container(border=True, key="card_results"):
    badge = f'<span class="tag orange">{brush_count:,} in brush</span>' if brush_count is not None else ""
    show(f'<div class="card-title">Results <span class="count">{total:,} rows</span> {badge}</div>')

    # Controls: sort column, direction and page number.
    columns = list(data.get_page(db, base_sql, 1, None, False).columns)
    sort_col, order_col, page_col, info_col = st.columns([2, 1.2, 1.2, 3], vertical_alignment="bottom")
    sort_by = sort_col.selectbox("Sort by", ["(no sorting)"] + columns)
    descending = order_col.toggle("Largest first", value=True)
    page = page_col.number_input("Page", min_value=1, max_value=page_count, key="page")
    first = (page - 1) * data.PAGE_SIZE + 1
    last = min(total, page * data.PAGE_SIZE)
    with info_col:
        show(f'<div class="meta right">Rows {first:,}–{last:,} of {total:,} · page {page} of {page_count:,}</div>')

    # Fetch only the 200 rows of this page from DuckDB.
    sort_column = None if sort_by == "(no sorting)" else sort_by
    rows = data.get_page(db, base_sql, page, sort_column, descending)
    rows.insert(0, "row", range(first, first + len(rows)))

    def highlight(row):
        """Pale yellow background for rows whose age is inside the brush."""
        inside = "age" in row and charts.is_in_brush(row["age"], brush)
        return ["background-color: #FFF3C4" if inside else ""] * len(row)

    styled = rows.style.apply(highlight, axis=1)
    if "income" in rows.columns:
        styled = styled.format({"income": "${:,.0f}"})  # 48348 -> $48,348
    labels = {column: column.upper() for column in rows.columns}  # column titles in capitals
    labels["hours"] = "HRS/WK"
    st.dataframe(styled, hide_index=True, height=560, width="stretch", column_config=labels)