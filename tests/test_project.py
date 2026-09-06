import sqlite3
from pathlib import Path

from sqlalchemy import create_engine

from src.db_inspector import inspect_schema
from src.query_executor import execute_query
from src.response_formatter import analytical_fallback, build_conversation_context, is_analytical_question, should_show_raw_data
from src.sql_safety import validate_sql


def make_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
        conn.exec_driver_sql("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL, FOREIGN KEY(customer_id) REFERENCES customers(id))")
        conn.exec_driver_sql("INSERT INTO customers VALUES (1, 'Asha'), (2, 'Ravi')")
        conn.exec_driver_sql("INSERT INTO orders VALUES (1, 1, 10.5), (2, 1, 4.5), (3, 2, 7.0)")
    return engine


def test_schema_inspection_finds_columns_and_foreign_keys():
    schema = inspect_schema(make_engine())
    assert schema.table_names == {"customers", "orders"}
    orders = next(table for table in schema.tables if table.name == "orders")
    assert any(r.referred_table == "customers" for r in orders.relationships)


def test_safe_select_is_approved_and_limited():
    schema = inspect_schema(make_engine())
    result = validate_sql("SELECT name FROM customers", schema)
    assert result.approved
    assert "LIMIT" in result.sql.upper()


def test_destructive_and_unknown_queries_are_rejected():
    schema = inspect_schema(make_engine())
    assert not validate_sql("DROP TABLE customers", schema).approved
    assert not validate_sql("SELECT * FROM missing", schema).approved
    assert not validate_sql("SELECT 1; SELECT 2", schema).approved


def test_query_execution_returns_dataframe():
    frame = execute_query(make_engine(), "SELECT name FROM customers LIMIT 100", 100)
    assert list(frame["name"]) == ["Asha", "Ravi"]


def test_follow_up_context_and_explicit_data_requests():
    history = [
        {"role": "user", "content": "How many customers do we have?"},
        {"role": "assistant", "content": "We have 2 customers."},
    ]
    assert "How many customers do we have?" in build_conversation_context(history)
    assert should_show_raw_data("Show the customer table")
    assert not should_show_raw_data("Why did sales rise last month?")
    assert is_analytical_question("Which salesperson has the potential to get promoted and what is their percentage?")


def test_deterministic_summary_natural_phrasing():
    from src.response_formatter import deterministic_summary
    import pandas as pd

    df_names = pd.DataFrame({"salesperson": ["Neha", "Priya", "Rahul"]})
    summary = deterministic_summary("Who are the salespeople?", df_names)
    assert "salespeople are Neha, Priya, and Rahul." in summary
    assert "matching records" not in summary.lower()
    assert "the result is" not in summary.lower()

    df_count = pd.DataFrame({"count": [5]})
    summary_count = deterministic_summary("How many orders were placed?", df_count)
    assert "There are 5." in summary_count


def test_analytical_fallback_explains_available_metrics_without_inventing_them():
    import pandas as pd

    frame = pd.DataFrame([{"salesperson": "Sneha", "promotion_potential": 23.22, "deals": 12}])
    answer = analytical_fallback(frame)
    assert "Sneha" in answer
    assert "23.22" in answer
    assert "deals=12" in answer
    assert "official HR promotion probability" in answer


def test_sqlite_master_is_blocked_with_system_catalog_reason():
    schema = inspect_schema(make_engine())
    result = validate_sql("SELECT name FROM sqlite_master WHERE type='table'", schema)
    assert not result.approved
    assert "system catalog" in result.reason.lower()


def test_schema_info_question_detection_and_overview_generation():
    from src.response_formatter import build_database_overview, is_schema_info_question

    assert is_schema_info_question("give me information about this database")
    assert is_schema_info_question("Tell me about the database")
    assert is_schema_info_question("What tables are in this database?")
    assert not is_schema_info_question("How many customers do we have?")

    engine = make_engine()
    schema = inspect_schema(engine)
    overview = build_database_overview(engine, schema)
    assert "SQLite (Read-Only)" in overview
    assert "customers" in overview
    assert "orders" in overview
    assert "2 rows" in overview
    assert "3 rows" in overview
    assert "Primary Key" in overview


def test_chart_detection_and_matplotlib_generation():
    import pandas as pd
    from src.response_formatter import generate_bar_chart, is_chartable, should_show_chart

    assert should_show_chart("Show a bar graph of sales")
    assert should_show_chart("Can you plot the data?")
    assert should_show_chart("datavisualisation of customer orders")
    assert not should_show_chart("Who are the salespeople?")

    df = pd.DataFrame({"salesperson": ["Neha", "Priya", "Rahul"], "sales": [1200, 1850, 950]})
    assert is_chartable(df)
    assert not is_chartable(pd.DataFrame({"salesperson": ["Neha"]}))

    fig = generate_bar_chart(df)
    assert fig is not None


def test_duplicate_columns_handling():
    import pandas as pd
    from src.query_executor import _deduplicate_columns
    from src.response_formatter import deterministic_summary

    cols = _deduplicate_columns(["id", "name", "id", "name", "id"])
    assert cols == ["id", "name", "id_1", "name_1", "id_2"]

    # Test deterministic_summary with duplicate columns (e.g. from JOINs)
    df_dup = pd.DataFrame(
        [["Sneha", "Sneha", 50], ["Priya", "Priya", 80]],
        columns=["name", "name", "score"]
    )
    summary = deterministic_summary("Who are the top performers?", df_dup)
    assert "Sneha" in summary
    assert "Priya" in summary


def test_dynamic_chart_types_detection():
    from src.chart_engine import detect_chart_type, extract_specific_chart_type

    assert detect_chart_type("Show a pie chart of sales") == "pie"
    assert detect_chart_type("Generate a donut chart of market share") == "pie"
    assert detect_chart_type("Plot a line chart of revenue trends") == "line"
    assert detect_chart_type("Show area chart of monthly expenses") == "area"
    assert detect_chart_type("Create a scatterplot of price vs rating") == "scatter"
    assert detect_chart_type("Show histogram of transaction amounts") == "histogram"
    assert detect_chart_type("Show distribution of customer ages") == "histogram"
    assert detect_chart_type("Show a bar graph of top products") == "bar"
    assert detect_chart_type("column chart of units sold") == "bar"
    assert detect_chart_type("visualize customer distribution") == "histogram"
    assert detect_chart_type("Can you plot the data?") == "bar"
    assert detect_chart_type("What is the total revenue?") is None

    # Verify specific types extract correctly
    assert extract_specific_chart_type("plot a line chart") == "line"
    assert extract_specific_chart_type("plot a scatter plot") == "scatter"
    assert extract_specific_chart_type("Can you plot this?") is None


def test_column_identification():
    import pandas as pd
    from src.chart_engine import identify_chart_columns

    df_cat_num = pd.DataFrame({"product": ["A", "B"], "revenue": [100, 200]})
    cat_col, num_cols = identify_chart_columns(df_cat_num)
    assert cat_col == "product"
    assert num_cols == ["revenue"]

    df_multi_num = pd.DataFrame({"orders": [5, 10], "revenue": [100, 200]})
    cat_col, num_cols = identify_chart_columns(df_multi_num)
    assert cat_col == "orders"
    assert num_cols == ["revenue"]


def test_dynamic_plotly_generation_all_types():
    import pandas as pd
    from src.chart_engine import generate_dynamic_chart

    df = pd.DataFrame({
        "salesperson": ["Neha", "Priya", "Rahul"],
        "sales": [1200, 1850, 950],
        "deals": [12, 18, 9],
    })

    # 1. Pie chart
    fig_pie = generate_dynamic_chart(df, question="show a pie chart of sales")
    assert fig_pie is not None
    assert fig_pie.data[0].type == "pie"

    # 2. Line chart
    fig_line = generate_dynamic_chart(df, question="show a line chart of sales")
    assert fig_line is not None
    assert fig_line.data[0].type == "scatter"
    assert fig_line.data[0].mode == "lines+markers"

    # 3. Area chart
    fig_area = generate_dynamic_chart(df, question="show area chart of sales")
    assert fig_area is not None
    assert fig_area.data[0].type == "scatter"
    assert fig_area.data[0].stackgroup is not None

    # 4. Scatter plot
    fig_scatter = generate_dynamic_chart(df, question="scatter plot of deals vs sales")
    assert fig_scatter is not None
    assert fig_scatter.data[0].type == "scatter"
    assert fig_scatter.data[0].mode == "markers"

    # 5. Histogram
    fig_hist = generate_dynamic_chart(df, question="show histogram of sales")
    assert fig_hist is not None
    assert fig_hist.data[0].type == "histogram"

    # 6. Bar chart
    fig_bar = generate_dynamic_chart(df, question="show a bar chart of sales")
    assert fig_bar is not None
    assert fig_bar.data[0].type == "bar"

    # Default fallback to bar on generic visualize keyword
    fig_generic = generate_dynamic_chart(df, question="visualize the sales")
    assert fig_generic is not None
    assert fig_generic.data[0].type == "bar"

    # LLM response intent detection takes priority over generic user request
    fig_llm = generate_dynamic_chart(df, question="plot the data", assistant_response="Here is a line chart showing sales")
    assert fig_llm is not None
    assert fig_llm.data[0].type == "scatter"

    # Graceful fallback: text-only dataframe returns None (triggers st.dataframe fallback in UI)
    df_text = pd.DataFrame({"name": ["Alice", "Bob"]})
    assert generate_dynamic_chart(df_text, question="pie chart") is None
    assert generate_dynamic_chart(pd.DataFrame(), question="pie chart") is None


def test_plotly_dark_and_tooltip_contrast():
    import pandas as pd
    from src.chart_engine import generate_dynamic_chart

    df = pd.DataFrame({
        "salesperson": ["Neha", "Priya"],
        "sales": [1200, 1850],
    })

    # Test across all chart types that plotly_dark and tooltip contrast styling apply
    for chart_type_query in [
        "pie chart",
        "line chart",
        "area chart",
        "scatter plot",
        "histogram",
        "bar chart",
    ]:
        fig = generate_dynamic_chart(df, question=chart_type_query)
        assert fig is not None, f"Failed to generate {chart_type_query}"
        # Verify hoverlabel styling
        assert fig.layout.hoverlabel.bgcolor == "#1f2937"
        assert fig.layout.hoverlabel.font.color == "#ffffff"
        assert fig.layout.hoverlabel.font.size == 13
