import os
import tempfile 
import time

import duckdb
import streamlit as st

PAGE_SIZE = 200
SAMPLE_SIZE = 2000

def create_database():
    """creates an empty in-memory databse. A table is added when someone uploads a file."""
    return duckdb.connect()

def load_uploaded_file(db, uploaded_file):
    """Saves an uploaded CSV/Parquet file to disk and loads it as a new table. Returns table name"""
    name = os.path.splitext(uploaded_file.name)[0].lower()
    table_name= "".join(letter if letter.isalnum() else "_" for letter in name).strip("_") or "data"
    if table_name[0].isdigit():
        table_name="t_"+ table_name

    extension=os.path.splitext(uploaded_file.name)[1].lower()
    path=os.path.join(tempfile.gettempdir(),"census_upload" + extension)
    with open(path, "wb") as file:
        file.write(uploaded_file.getvalue())
    reader="read_parquet" if extension == ".parquet" else "read_csv_auto"
    db.execute(f"CREATE OR REPLACE TABLE \"{table_name}\" AS SELECT * FROM {reader}('{path}')")
    return table_name

def describe_table(db,table_name):
    """Returns(row count,colum count) of table for header"""
    rows=db.execute(f'SELECT count(*)FROM"{table_name}"').fetchone()[0]
    columns=len(db.execute(f'SELECT * FROM"{table_name}" LIMIT 0').df().columns)
    return rows,columns

def clean_sql(sql):
        """Removes spaces and trailing so the query can be wrapped in(...)"""
        return sql.strip().rstrip(";").strip()

def count_rows(db,sql):
    """Runs the users's query and counts its raws. Returns(count, milliseconds)."""
    start=time.time()
    count=db.execute(f"SELECT count(*) FROM({sql}) AS q").fetchone()[0]
    milliseconds =(time.time()-start) * 1000
    return count, milliseconds 

def export_csv(db,sql):
    """writed the whole query results to CSV file with DuckDB's COPY,the returns its bytes."""
    path=os.path.join(tempfile.gettempdir(),"census_export.csv")
    db.execute(f"COPY ({sql}) TO '{path}' (HEADER,DELIMITER',')")
    with open(path,"rb") as file:
        return file.read()
# ---------- Step 5: results table ----------


@st.cache_data(max_entries=50)
def get_page(_db, sql, page, sort_column, descending):
    """Returns one page (200 rows) of the query result as a pandas DataFrame.

    The _ in _db tells Streamlit's cache to ignore that argument.
    Page 1 = rows 1-200, page 2 = rows 201-400, and so on.
    """
    order = ""
    if sort_column:
        direction = "DESC" if descending else "ASC"
        order = f'ORDER BY "{sort_column}" {direction} NULLS LAST'
    offset = (page - 1) * PAGE_SIZE
    return _db.execute(f"SELECT * FROM ({sql}) AS q {order} LIMIT {PAGE_SIZE} OFFSET {offset}").df()


# ---------- Step 6: histogram and brush ----------


@st.cache_data(max_entries=50)
def histogram(_db, sql):
    """Counts people in 4-year age groups: 16-19, 20-23, 24-27, ..."""
    return _db.execute(f"""
        SELECT floor(age / 4) * 4 AS bin_start, count(*) AS people
        FROM ({sql}) AS q
        WHERE age IS NOT NULL
        GROUP BY 1
        ORDER BY 1
    """).df()


def count_in_brush(db, sql, low, high):
    """How many rows of the query have an age inside the brush."""
    return db.execute(f"SELECT count(*) FROM ({sql}) AS q WHERE age BETWEEN {low} AND {high}").fetchone()[0]


# ---------- Step 7: scatter plot ----------


@st.cache_data(max_entries=50)
def scatter_sample(_db, sql):
    """A random sample of 2,000 rows (the same sample every time, thanks to REPEATABLE)."""
    return _db.execute(f"""
        SELECT age, income
        FROM ({sql}) AS q
        USING SAMPLE reservoir({SAMPLE_SIZE} ROWS) REPEATABLE (42)
    """).df()