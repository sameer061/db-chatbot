from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


def _deduplicate_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    deduped: list[str] = []
    for col in columns:
        count = seen.get(col, 0)
        seen[col] = count + 1
        deduped.append(col if count == 0 else f"{col}_{count}")
    return deduped


def execute_query(engine: Engine, sql: str, max_rows: int) -> pd.DataFrame:
    with engine.connect() as connection:
        result = connection.execute(text(sql))
        rows = result.fetchmany(max_rows)
        columns = _deduplicate_columns(list(result.keys()))
        return pd.DataFrame(rows, columns=columns)
