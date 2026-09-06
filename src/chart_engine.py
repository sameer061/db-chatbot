from __future__ import annotations

import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

__all__ = [
    "detect_chart_type",
    "should_show_chart",
    "prepare_chart_dataframe",
    "is_chartable",
    "identify_chart_columns",
    "generate_dynamic_chart",
]


def extract_specific_chart_type(text: str) -> str | None:
    """Detect specific chart type keywords, ignoring generic plot/graph terms."""
    if not text:
        return None
    lower = text.lower()
    if re.search(r"\b(pie|piechart|donut|doughnut)\b", lower):
        return "pie"
    if re.search(r"\b(scatter|scatterplot)\b", lower):
        return "scatter"
    if re.search(r"\b(area|areachart)\b", lower):
        return "area"
    if re.search(r"\b(histogram|distribution|hist)\b", lower):
        return "histogram"
    if re.search(r"\b(line|linechart|trend|trends)\b", lower):
        return "line"
    if re.search(r"\b(bar|barchart|column|columnchart)\b", lower):
        return "bar"
    return None


def detect_chart_type(text: str) -> str | None:
    """Parse text (query or assistant response) for chart keywords."""
    specific = extract_specific_chart_type(text)
    if specific:
        return specific

    if not text:
        return None
    lower = text.lower()
    if any(k in lower for k in ["chart", "plot", "graph", "visualize", "visualise", "visualization", "visualisation", "datavisualisation"]):
        return "bar"

    return None


def should_show_chart(question: str, assistant_response: str = "") -> bool:
    """Check if the user question or assistant response requests visualization."""
    return bool(detect_chart_type(question) or detect_chart_type(assistant_response))


def prepare_chart_dataframe(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    """Clean and cast columns in dataframe for plotting."""
    if frame is None or frame.empty or len(frame) < 1:
        return None

    df = frame.copy()

    # Deduplicate column names if needed
    seen: dict[str, int] = {}
    deduped = []
    for col in df.columns:
        count = seen.get(col, 0)
        seen[col] = count + 1
        deduped.append(col if count == 0 else f"{col}_{count}")
    df.columns = deduped

    # Auto-convert string columns that are numeric
    for col in df.columns:
        if df[col].dtype == "object":
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() >= len(df) * 0.5:
                df[col] = converted

    return df


def is_chartable(frame: pd.DataFrame | None) -> bool:
    """Check if dataframe has enough data and numeric columns to plot."""
    df = prepare_chart_dataframe(frame)
    if df is None or len(df) < 1:
        return False
    numeric_cols = df.select_dtypes(include=["number"]).columns
    return len(numeric_cols) > 0


def identify_chart_columns(df: pd.DataFrame) -> tuple[str | None, list[str]]:
    """Identify categorical (X-axis/Labels) and numerical (Y-axis/Values) columns."""
    numeric_cols = list(df.select_dtypes(include=["number"]).columns)
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

    cat_col = None
    if non_numeric_cols:
        cat_col = non_numeric_cols[0]
    elif len(numeric_cols) > 1:
        cat_col = numeric_cols[0]
        numeric_cols = numeric_cols[1:]
    elif numeric_cols:
        cat_col = df.index.name or "Item"

    return cat_col, numeric_cols


def generate_dynamic_chart(
    frame: pd.DataFrame,
    question: str = "",
    assistant_response: str = "",
    title: str | None = None,
) -> go.Figure | None:
    """Generate the requested Plotly figure dynamically based on keywords."""
    df = prepare_chart_dataframe(frame)
    if df is None:
        return None

    # Priority: explicit specific type in question -> explicit specific type in response -> generic in either -> fallback to bar
    chart_type = (
        extract_specific_chart_type(question)
        or extract_specific_chart_type(assistant_response)
        or detect_chart_type(question)
        or detect_chart_type(assistant_response)
        or "bar"
    )
    cat_col, numeric_cols = identify_chart_columns(df)

    if not numeric_cols:
        return None

    num_col = numeric_cols[0]
    if cat_col:
        default_title = f"{num_col.replace('_', ' ').title()} by {str(cat_col).replace('_', ' ').title()}"
    else:
        default_title = num_col.replace('_', ' ').title()
    chart_title = title or default_title

    # For pie or bar charts, cap to top 30 rows for readability; keep full rows for distributions/trends
    if chart_type in ("pie", "bar") and len(df) > 30:
        df_plot = df.head(30).copy()
    else:
        df_plot = df.copy()

    # If synthetic cat_col was selected and doesn't exist, create it in df_plot
    if cat_col and cat_col not in df_plot.columns:
        df_plot[cat_col] = [f"Item {i+1}" for i in range(len(df_plot))]

    try:
        if chart_type == "pie":
            if not cat_col:
                return None
            fig = px.pie(
                df_plot,
                names=cat_col,
                values=num_col,
                title=chart_title,
                hole=0.3,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")

        elif chart_type == "line":
            fig = px.line(
                df_plot,
                x=cat_col,
                y=num_col,
                title=chart_title,
                markers=True,
            )

        elif chart_type == "area":
            fig = px.area(
                df_plot,
                x=cat_col,
                y=num_col,
                title=chart_title,
            )

        elif chart_type == "scatter":
            if len(numeric_cols) >= 2:
                col1, col2 = numeric_cols[0], numeric_cols[1]
                scatter_title = title or f"{col2.replace('_', ' ').title()} vs {col1.replace('_', ' ').title()}"
                fig = px.scatter(
                    df_plot,
                    x=col1,
                    y=col2,
                    hover_name=cat_col if cat_col and cat_col in df_plot.columns else None,
                    title=scatter_title,
                )
            else:
                fig = px.scatter(
                    df_plot,
                    x=cat_col,
                    y=num_col,
                    title=chart_title,
                )

        elif chart_type == "histogram":
            if cat_col and cat_col in df_plot.columns and cat_col != num_col:
                fig = px.histogram(
                    df_plot,
                    x=cat_col,
                    y=num_col,
                    title=chart_title,
                )
            else:
                fig = px.histogram(
                    df_plot,
                    x=num_col,
                    title=chart_title,
                )

        else:  # "bar" and default fallback
            fig = px.bar(
                df_plot,
                x=cat_col,
                y=num_col,
                title=chart_title,
                text_auto=True,
            )

        fig.update_traces(
            hoverlabel=dict(
                bgcolor="#1f2937",
                font_color="#ffffff",
                font_size=13,
            )
        )
        fig.update_layout(
            template="plotly_dark",
            margin=dict(l=40, r=40, t=50, b=40),
            title_font=dict(size=14, family="sans-serif"),
            hoverlabel=dict(
                bgcolor="#1f2937",  # Dark gray background
                font_color="#ffffff",  # Pure white text
                font_size=13,
            ),
        )
        return fig
    except Exception:
        return None
