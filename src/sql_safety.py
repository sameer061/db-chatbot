from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from .config import DESTRUCTIVE_KEYWORDS, settings
from .db_inspector import DatabaseSchema


@dataclass
class ValidationResult:
    approved: bool
    sql: str | None = None
    reason: str | None = None


def _strip_code_fence(raw: str) -> str:
    text = raw.strip()
    match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", text, flags=re.I)
    if match:
        text = match.group(1).strip()
    else:
        text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    select_match = re.search(r"\b(SELECT\b[\s\S]*)", text, flags=re.I)
    if select_match:
        text = select_match.group(1)
    return text.strip()


def _known_columns(schema: DatabaseSchema) -> dict[str, set[str]]:
    return {table.name.lower(): {c.name.lower() for c in table.columns} for table in schema.tables}


def _add_limit(statement: exp.Expression) -> str:
    if isinstance(statement, exp.Select) and statement.args.get("limit") is None:
        statement = statement.limit(settings.max_rows)
    return statement.sql(dialect="sqlite")


def validate_sql(raw_sql: str, schema: DatabaseSchema) -> ValidationResult:
    sql = _strip_code_fence(raw_sql)
    if not sql:
        return ValidationResult(False, reason="The model returned no SQL.")
    if ";" in sql.rstrip(";"):
        return ValidationResult(False, reason="Multiple SQL statements are not allowed.")
    first_word = re.match(r"\s*([A-Za-z]+)", sql)
    if not first_word or first_word.group(1).upper() != "SELECT":
        return ValidationResult(False, reason="Only read-only SELECT queries are allowed.")
    if any(re.search(rf"\b{re.escape(word)}\b", sql, re.I) for word in DESTRUCTIVE_KEYWORDS):
        return ValidationResult(False, reason="The query contains a blocked operation.")
    try:
        statements = sqlglot.parse(sql, read="sqlite")
        if len(statements) != 1:
            return ValidationResult(False, reason="Exactly one SQL statement is required.")
        statement = statements[0]
        if not isinstance(statement, exp.Select):
            return ValidationResult(False, reason="Only SELECT statements are allowed.")
    except Exception as exc:
        return ValidationResult(False, reason=f"SQL could not be parsed: {exc}")

    SYSTEM_CATALOG_TABLES = {"sqlite_master", "sqlite_schema", "sqlite_temp_master", "sqlite_temp_schema", "information_schema"}
    known_tables = {name.lower() for name in schema.table_names}
    known_columns = _known_columns(schema)
    for table in statement.find_all(exp.Table):
        table_name_lower = table.name.lower()
        if table_name_lower in SYSTEM_CATALOG_TABLES:
            return ValidationResult(
                False,
                reason=f"Querying system catalog table '{table.name}' is not permitted. Query only user tables from the discovered schema: {', '.join(sorted(schema.table_names))}.",
            )
        if table_name_lower not in known_tables:
            return ValidationResult(False, reason=f"Unknown table: {table.name}")
    for column in statement.find_all(exp.Column):
        if column.table and column.table.lower() in known_columns and column.name.lower() not in known_columns[column.table.lower()]:
            return ValidationResult(False, reason=f"Unknown column: {column.table}.{column.name}")
    return ValidationResult(True, sql=_add_limit(statement))
