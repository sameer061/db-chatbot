from .db_inspector import DatabaseSchema


def build_schema_context(schema: DatabaseSchema) -> str:
    lines = ["Database dialect: SQLite", "Available schema:"]
    for table in schema.tables:
        columns = ", ".join(
            f"{column.name} ({column.data_type})" + (" PRIMARY KEY" if column.primary_key else "")
            for column in table.columns
        )
        lines.append(f"TABLE {table.name}: {columns}")
        for relationship in table.relationships:
            lines.append(
                f"RELATIONSHIP {relationship.table}.{relationship.column} = "
                f"{relationship.referred_table}.{relationship.referred_column}"
            )
    return "\n".join(lines)
