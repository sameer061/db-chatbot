from __future__ import annotations

import pandas as pd

__all__ = [
    "deterministic_summary",
    "analytical_fallback",
    "is_generic_summary",
    "build_conversation_context",
    "should_show_raw_data",
    "should_show_sql",
    "should_show_chart",
    "is_chartable",
    "generate_bar_chart",
    "is_analytical_question",
    "is_schema_info_question",
    "infer_table_description",
    "build_database_overview",
    "result_as_text",
]


def deterministic_summary(question: str, frame: pd.DataFrame) -> str:
    if frame.empty:
        return "I could not find any records in the database matching that query."

    # Single value result (1 row, 1 column)
    if len(frame) == 1 and len(frame.columns) == 1:
        val = frame.iloc[0, 0]
        col = str(frame.columns[0]).lower()
        q_lower = question.lower()
        if any(term in col for term in ["count", "total", "sum"]) or any(term in q_lower for term in ["how many", "total", "count"]):
            return f"There are {val}."
        return f"{val}."

    # Single column with multiple rows (e.g. list of names/items)
    if len(frame.columns) == 1:
        col_name = str(frame.columns[0])
        col_series = frame.iloc[:, 0]
        values = [str(v) for v in col_series.dropna().tolist() if str(v).strip()]
        if not values:
            return "No matching entries were found."
        if len(values) == 1:
            return f"{values[0]}."
        elif len(values) <= 12:
            joined = ", ".join(values[:-1]) + f", and {values[-1]}"
            col_clean = col_name.replace("_", " ").lower()
            if any(term in col_clean for term in ["salesperson", "employee", "representative", "staff"]):
                return f"The salespeople are {joined}."
            elif "name" in col_clean:
                return f"The names are {joined}."
            return f"The {col_clean} are {joined}."
        else:
            first_few = ", ".join(values[:10])
            return f"The {col_name.replace('_', ' ').lower()} include {first_few}, and {len(values) - 10} others."

    # Single row with multiple attributes
    if len(frame) == 1:
        row = frame.iloc[0]
        name_col = next((c for c in frame.columns if any(t in c.lower() for t in ["name", "salesperson", "employee", "customer"])), None)
        def _cell_val(col):
            v = row[col]
            return v.iloc[0] if isinstance(v, pd.Series) else v
        entity = str(_cell_val(name_col)) if name_col else "The matching record"
        details = [f"{c.replace('_', ' ')} is {_cell_val(c)}" for c in frame.columns if c != name_col and pd.notna(_cell_val(c))]
        return f"{entity} ({', '.join(details)})."

    # Multiple rows with multiple columns
    entity_col = next((c for c in frame.columns if any(t in c.lower() for t in ["name", "salesperson", "customer", "product", "title"])), frame.columns[0])
    col_data = frame[entity_col]
    if isinstance(col_data, pd.DataFrame):
        col_data = col_data.iloc[:, 0]
    entities = [str(v) for v in col_data.dropna().tolist()[:6]]
    if entities:
        return f"The relevant entries include {', '.join(entities)}."
    return "Here are the relevant details from the database."


def analytical_fallback(frame: pd.DataFrame) -> str:
    """Explain an analytical result without inventing unavailable metrics."""
    if frame.empty:
        return "I could not identify a recommendation because no matching records were found."

    row = frame.iloc[0]
    name_column = next(
        (column for column in frame.columns if any(term in column.lower() for term in ["salesperson", "employee", "representative", "name"])),
        None,
    )
    score_column = next(
        (column for column in frame.columns if any(term in column.lower() for term in ["potential", "score", "percentage", "percent"])),
        None,
    )

    def _val(col):
        v = row[col]
        return str(v.iloc[0]) if isinstance(v, pd.Series) else str(v)

    person = _val(name_column) if name_column else "the top candidate"
    score = f" at {_val(score_column)}" if score_column else ""
    metric_columns = [column for column in frame.columns if column not in {name_column, score_column}]
    metric_text = ", ".join(f"{column}={_val(column)}" for column in metric_columns[:6])

    answer = f"Based on the available database results, {person} ranks first with an estimated promotion-potential score{score}."
    if metric_text:
        answer += f" The supporting available metrics are {metric_text}."
    answer += " This is a data-based interpretation, not an official HR promotion probability."
    if not score_column:
        answer += " The result does not include a promotion score or percentage, so I cannot calculate one without a defined scoring method and the required metrics."
    return answer


def is_generic_summary(answer: str) -> bool:
    return answer.strip().lower() == "i found the relevant records and summarized them below in plain english."


def build_conversation_context(messages: list[dict] | None, max_entries: int = 8) -> str:
    if not messages:
        return "No prior conversation."
    recent = list(messages)[-max_entries:]
    parts: list[str] = []
    for message in recent:
        role = str(message.get("role", "user")).strip()
        content = str(message.get("content", "")).strip()
        if content:
            parts.append(f"{role.title()}: {content}")
    return "\n".join(parts) if parts else "No prior conversation."


def should_show_raw_data(question: str) -> bool:
    text = question.lower()
    explicit_markers = [
        "show the table",
        "show table",
        "show raw data",
        "raw data",
        "display the data",
        "show the rows",
        "show data",
        "list all rows",
        "list the records",
        "dump the data",
        "show the full table",
        "show all records",
        "display all data",
    ]
    if any(marker in text for marker in explicit_markers):
        return True
    if any(word in text for word in ["table", "rows", "records", "data"]) and any(word in text for word in ["show", "display", "list", "fetch", "view"]):
        return True
    return False


def should_show_sql(question: str) -> bool:
    text = question.lower()
    return any(marker in text for marker in ["show sql", "generated sql", "show the query", "display query", "show query"])


from .chart_engine import (
    detect_chart_type,
    generate_dynamic_chart,
    is_chartable,
    should_show_chart,
)


def generate_bar_chart(frame: pd.DataFrame, title: str | None = None):
    """Generate a chart figure (defaults to bar chart)."""
    return generate_dynamic_chart(frame, question="bar", title=title)


def is_analytical_question(question: str) -> bool:
    text = question.lower()
    analytical_markers = [
        "potential to get promoted",
        "promotion potential",
        "who should be promoted",
        "top performer",
        "best salesperson",
        "recommendation",
        "analyze",
        "analysis",
        "compare",
        "benchmark",
        "performance",
        "why did",
        "what is driving",
        "what explains",
        "insight",
        "trend",
        "growth",
        "consistency",
    ]
    return any(marker in text for marker in analytical_markers)


def is_schema_info_question(question: str) -> bool:
    text = question.strip().lower()
    info_markers = [
        "information about this database",
        "information about the database",
        "info about this database",
        "info about the database",
        "tell me about this database",
        "tell me about the database",
        "what is this database about",
        "what is the database about",
        "what does this database contain",
        "what tables are in this database",
        "what tables are in the database",
        "what tables exist",
        "what tables do we have",
        "which tables are in this database",
        "list all tables",
        "list the tables",
        "list tables",
        "show all tables",
        "show tables",
        "describe the database",
        "describe database",
        "explain the database",
        "database structure",
        "database schema",
        "show schema",
        "what is the schema",
        "database overview",
        "database info",
        "overview of the database",
        "overview of this database",
    ]
    if any(marker in text for marker in info_markers):
        return True

    has_db = any(term in text for term in ["database", "db"])
    has_info = any(term in text for term in ["information", "info", "overview", "structure", "schema", "summary", "about", "tables"])
    has_query_action = any(term in text for term in ["what", "tell", "give", "describe", "explain", "show", "list"])
    return has_db and has_info and has_query_action


def infer_table_description(table_name: str, column_names: list[str]) -> str:
    name_lower = table_name.lower()
    cols_lower = [c.lower() for c in column_names]

    if any(term in name_lower for term in ["customer", "client", "user", "account"]):
        return "Stores customer profiles and account identity records."
    elif any(term in name_lower for term in ["order", "transaction", "sale", "invoice", "purchase"]):
        return "Records sales transactions, order amounts, and customer references."
    elif any(term in name_lower for term in ["product", "item", "inventory", "stock"]):
        return "Catalog of products, inventory specifications, and unit prices."
    elif any(term in name_lower for term in ["employee", "staff", "salesperson", "worker", "rep"]):
        return "Records staff details, department assignments, and sales representatives."
    elif any(term in name_lower for term in ["log", "audit", "history"]):
        return "Historical system actions, audit trails, and tracking logs."

    if any("price" in c or "amount" in c or "cost" in c for c in cols_lower):
        return f"Stores {table_name} data with pricing or financial measurements."
    return f"Stores {table_name} records containing: {', '.join(column_names[:5])}."


def build_database_overview(engine, schema) -> str:
    if not schema or not schema.tables:
        return (
            "I can't safely inspect the database schema with the currently available database interface. "
            "Please provide the schema or enable schema/metadata inspection."
        )

    lines: list[str] = [
        "### Database Overview",
        "",
        "- **Database Engine:** SQLite (Read-Only)",
        f"- **Discovered Tables:** {len(schema.tables)} ({', '.join(f'`{t.name}`' for t in schema.tables)})",
        "",
        "---",
        "",
    ]

    all_relationships: list[str] = []

    for table in schema.tables:
        col_names = [col.name for col in table.columns]
        desc = infer_table_description(table.name, col_names)

        row_count_str = "unknown count"
        if engine is not None:
            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    count = conn.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
                    row_count_str = f"{count:,} rows"
            except Exception:
                pass

        lines.append(f"#### Table: `{table.name}` ({row_count_str})")
        lines.append(f"*{desc}*")
        lines.append("")

        pk_cols = [c.name for c in table.columns if c.primary_key]
        if pk_cols:
            lines.append(f"- **Primary Key:** `{', '.join(pk_cols)}`")

        col_details = []
        for c in table.columns:
            pk_mark = " [PK]" if c.primary_key else ""
            null_mark = "NOT NULL" if not c.nullable else "NULL"
            col_details.append(f"`{c.name}` ({c.data_type}, {null_mark}{pk_mark})")

        lines.append(f"- **Columns:** {', '.join(col_details)}")

        if table.relationships:
            rel_strings = [
                f"`{r.column}` → `{r.referred_table}.{r.referred_column}`"
                for r in table.relationships
            ]
            lines.append(f"- **Foreign Keys:** {', '.join(rel_strings)}")
            for r in table.relationships:
                all_relationships.append(f"- `{table.name}.{r.column}` references `{r.referred_table}.{r.referred_column}`")

        lines.append("")

    if all_relationships:
        lines.append("---")
        lines.append("#### Important Relationships")
        lines.extend(all_relationships)
        lines.append("")

    return "\n".join(lines)


def result_as_text(frame: pd.DataFrame, max_chars: int = 2000) -> str:
    return frame.to_csv(index=False)[:max_chars]
