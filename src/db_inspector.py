from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from .config import ALLOWED_SUFFIXES


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False


class RelationshipInfo(BaseModel):
    table: str
    column: str
    referred_table: str
    referred_column: str


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo] = Field(default_factory=list)
    relationships: list[RelationshipInfo] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    tables: list[TableInfo] = Field(default_factory=list)

    @property
    def table_names(self) -> set[str]:
        return {table.name for table in self.tables}


def save_upload(uploaded_file: BinaryIO, original_name: str) -> Path:
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Please upload a SQLite file ending in .db, .sqlite, or .sqlite3.")
    with tempfile.NamedTemporaryFile(prefix="local_db_", suffix=suffix, delete=False) as handle:
        handle.write(uploaded_file.read())
        return Path(handle.name)


def create_engine_read_only(path: Path) -> Engine:
    uri = f"sqlite:///file:{path}?mode=ro&uri=true"
    engine = create_engine(uri, connect_args={"check_same_thread": False})
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return engine


def inspect_schema(engine: Engine) -> DatabaseSchema:
    inspector = inspect(engine)
    tables: list[TableInfo] = []
    for table_name in inspector.get_table_names():
        primary_keys = set(inspector.get_pk_constraint(table_name).get("constrained_columns") or [])
        columns = [
            ColumnInfo(
                name=column["name"],
                data_type=str(column.get("type", "unknown")),
                nullable=bool(column.get("nullable", True)),
                primary_key=column["name"] in primary_keys,
            )
            for column in inspector.get_columns(table_name)
        ]
        relationships: list[RelationshipInfo] = []
        for fk in inspector.get_foreign_keys(table_name):
            for column, referred in zip(fk.get("constrained_columns", []), fk.get("referred_columns", [])):
                relationships.append(RelationshipInfo(table=table_name, column=column, referred_table=fk["referred_table"], referred_column=referred))
        tables.append(TableInfo(name=table_name, columns=columns, relationships=relationships))
    return DatabaseSchema(tables=tables)


def validate_sqlite_file(path: Path) -> None:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("The uploaded SQLite database did not pass integrity checks.")
    except sqlite3.Error as exc:
        raise ValueError("The uploaded file is not a readable SQLite database.") from exc
