from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import sys

# Ensure local src submodules are reloaded fresh on Streamlit reruns
for mod in ["src.config", "src.db_inspector", "src.query_executor", "src.response_formatter", "src.chart_engine", "src.schema_context", "src.sql_generator", "src.sql_safety"]:
    if mod in sys.modules:
        importlib.reload(sys.modules[mod])

import streamlit as st

from src.chart_engine import (
    detect_chart_type,
    generate_dynamic_chart,
    is_chartable,
    should_show_chart,
)
from src.config import settings
from src.db_inspector import create_engine_read_only, inspect_schema, save_upload, validate_sqlite_file
from src.query_executor import execute_query
from src.response_formatter import (
    analytical_fallback,
    build_conversation_context,
    build_database_overview,
    deterministic_summary,
    is_analytical_question,
    is_generic_summary,
    is_schema_info_question,
    result_as_text,
    should_show_raw_data,
    should_show_sql,
)
from src.schema_context import build_schema_context
from src.sql_generator import generate_sql, get_available_models, summarize_result
from src.sql_safety import validate_sql


def render_frame(frame):
    if frame is None or frame.empty:
        st.write("No rows returned.")
        return
    st.markdown(frame.to_html(index=False, border=0), unsafe_allow_html=True)


def render_chart(frame, question="", assistant_response=""):
    try:
        fig = generate_dynamic_chart(frame, question=question, assistant_response=assistant_response)
        if fig is not None:
            fig.update_layout(
                template="plotly_dark",
                hoverlabel=dict(
                    bgcolor="#1f2937",  # Dark gray background
                    font_color="#ffffff",  # Pure white text
                    font_size=13,
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
            return
    except Exception:
        pass
    if frame is not None and not frame.empty:
        st.dataframe(frame, use_container_width=True)


st.set_page_config(page_title="Local Database Chatbot", page_icon="DB", layout="wide")
st.title("Local Database Chatbot")
st.caption("Upload a SQLite database and ask questions using a local Ollama model.")

if "db_path" not in st.session_state:
    st.session_state.db_path = None
    st.session_state.engine = None
    st.session_state.schema = None
    st.session_state.schema_context = None
    st.session_state.messages = []

with st.sidebar:
    st.header("Database")
    upload = st.file_uploader("Upload SQLite database", type=["db", "sqlite", "sqlite3"])
    if upload is not None:
        upload_key = hashlib.sha256(upload.getvalue()).hexdigest()
        if st.session_state.get("upload_key") != upload_key:
            try:
                path = save_upload(upload, upload.name)
                validate_sqlite_file(path)
                engine = create_engine_read_only(path)
                schema = inspect_schema(engine)
                st.session_state.update(
                    upload_key=upload_key,
                    db_path=path,
                    engine=engine,
                    schema=schema,
                    schema_context=build_schema_context(schema),
                    messages=[],
                )
                st.success(f"Loaded {upload.name}")
            except Exception as exc:
                st.error(str(exc))
    if st.session_state.schema:
        schema = st.session_state.schema
        st.write(f"**Tables:** {len(schema.tables)}")
        with st.expander("Discovered schema"):
            st.code(st.session_state.schema_context)
        if st.button("Clear database"):
            for key in ("db_path", "engine", "schema", "schema_context", "upload_key"):
                st.session_state[key] = None
            st.session_state.messages = []
            st.rerun()
    st.divider()
    st.subheader("Model Selection")
    available_models = get_available_models(settings.ollama_url)
    current_selected = st.session_state.get("selected_model", settings.model_name)
    if current_selected not in available_models:
        available_models.insert(0, current_selected)
    model_options = available_models + ["Custom model..."]

    selected_idx = model_options.index(current_selected) if current_selected in model_options else 0
    selected_choice = st.selectbox(
        "Active Model",
        options=model_options,
        index=selected_idx,
        help="Switch between local Ollama models (e.g. qwen2.5-coder:1.5b for speed or 7b for complex logic).",
    )
    if selected_choice == "Custom model...":
        active_model = st.text_input("Enter model tag", value=current_selected)
    else:
        active_model = selected_choice
    st.session_state.selected_model = active_model

    fast_mode = st.toggle(
        "Fast mode",
        value=True,
        help="Instant response mode: queries and displays data directly. Runs deep AI summarization only for analytical questions.",
    )
    st.caption(f"Active: `{active_model}` | Max rows: `{settings.max_rows}`")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("frame") is not None:
            if message.get("show_chart"):
                render_chart(
                    message["frame"],
                    question=message.get("chart_question", ""),
                    assistant_response=message.get("content", ""),
                )
            if message.get("show_raw"):
                render_frame(message["frame"])
            elif not message.get("show_chart") and len(message["frame"]) > 1:
                with st.expander("📊 View chart & data"):
                    tab_chart, tab_data = st.tabs(["Chart", "Data Table"])
                    with tab_chart:
                        render_chart(
                            message["frame"],
                            question=message.get("chart_question", ""),
                            assistant_response=message.get("content", ""),
                        )
                    with tab_data:
                        render_frame(message["frame"])
        if message.get("sql"):
            with st.expander("Generated SQL"):
                st.code(message["sql"], language="sql")

question = st.chat_input("Ask a question about the uploaded database")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    if not st.session_state.engine:
        answer = "Please upload a SQLite database first."
        st.session_state.messages.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.warning(answer)
        st.stop()

    if is_schema_info_question(question):
        with st.chat_message("assistant"):
            answer = build_database_overview(st.session_state.engine, st.session_state.schema)
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        st.stop()

    with st.chat_message("assistant"):
        with st.spinner("Executing query and fetching results..."):
            sql = None
            frame = None
            last_error = None
            conversation_context = build_conversation_context(st.session_state.messages)
            for attempt in range(settings.max_repair_attempts + 1):
                try:
                    sql = generate_sql(
                        question,
                        st.session_state.schema_context,
                        last_error,
                        sql,
                        conversation_context,
                        model=st.session_state.get("selected_model", settings.model_name),
                    )
                    validation = validate_sql(sql, st.session_state.schema)
                    if not validation.approved:
                        last_error = validation.reason
                        continue
                    sql = validation.sql
                    frame = execute_query(st.session_state.engine, sql, settings.max_rows)
                    break
                except Exception as exc:
                    last_error = str(exc)
            if frame is None:
                answer = f"I could not produce a safe, executable query. {last_error or ''}"
                st.error(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer, "sql": sql})
            else:
                answer = deterministic_summary(question, frame)
                if not frame.empty:
                    try:
                        max_chars = 1200 if fast_mode else 2500
                        answer = summarize_result(
                            question,
                            result_as_text(frame, max_chars=max_chars),
                            conversation_context,
                            model=st.session_state.get("selected_model", settings.model_name),
                        )
                    except Exception:
                        answer = analytical_fallback(frame) if is_analytical_question(question) else deterministic_summary(question, frame)
                if is_analytical_question(question) and is_generic_summary(answer):
                    answer = analytical_fallback(frame)
                st.markdown(answer)

                show_chart = should_show_chart(question, answer) and is_chartable(frame)
                show_raw = should_show_raw_data(question)

                if show_chart:
                    render_chart(frame, question=question, assistant_response=answer)

                if show_raw:
                    render_frame(frame)
                elif not show_chart and not frame.empty and len(frame) > 1:
                    if is_chartable(frame):
                        with st.expander("📊 View chart & data"):
                            tab_chart, tab_data = st.tabs(["Chart", "Data Table"])
                            with tab_chart:
                                render_chart(frame, question=question, assistant_response=answer)
                            with tab_data:
                                render_frame(frame)
                    else:
                        with st.expander("View supporting data"):
                            render_frame(frame)
                elif frame.empty:
                    st.caption("No matching records found.")

                show_sql = should_show_sql(question)
                if show_sql:
                    with st.expander("Generated SQL"):
                        st.code(sql, language="sql")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "frame": frame if (show_raw or show_chart or (not frame.empty and len(frame) > 1)) else None,
                    "show_chart": show_chart,
                    "show_raw": show_raw,
                    "chart_question": question,
                    "sql": sql if show_sql else None,
                })
