# Local Database Chatbot

A simple, private Text-to-SQL chatbot. Upload a SQLite database, ask a question in plain English, and receive a natural-language answer plus the actual result table.

## What you are building

The application follows this pipeline:

> **Upload → inspect schema → build schema context → generate SQL → validate → execute read-only → summarize → display.**

Streamlit provides the interface. SQLAlchemy connects to SQLite. The inspector discovers tables, columns, keys, and relationships, so the code does not contain database-specific table names. LlamaIndex and Ollama connect the schema context to a local language model. SQLGlot parses generated SQL before execution. The model is never trusted as a security boundary.

## Prerequisites

Install Python 3.11 or newer, Git, Ollama, and a SQLite file ending in `.db`, `.sqlite`, or `.sqlite3`. Use at least 8 GB RAM for a 4B-class model; 16 GB is recommended for the 7B default. A dedicated GPU is optional.

## Installation

From a terminal:

```bash
git clone <your-repository-url> local-db-chatbot
cd local-db-chatbot
python3 -m venv .venv
source .venv/bin/activate       # Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install Ollama from [ollama.com](https://ollama.com/), start it, then pull a model:

```bash
ollama pull qwen2.5-coder:7b
```

For a low-memory machine, try a current 4B-class Qwen model available in the Ollama library, for example:

```bash
ollama pull qwen3:4b
```

If the 4B tag is unavailable, choose the current Qwen instruct/coder model with a similar size and set its name in `.env`.

## Run

```bash
cp .env.example .env
streamlit run app.py
```

Open the local address printed by Streamlit, upload a database, and ask a question such as `How many customers are there?` or `Show the top 10 products by sales.`

## Project structure

`app.py` is the Streamlit entry point. `db_inspector.py` saves uploads and discovers schema metadata. `schema_context.py` turns that metadata into a compact prompt. `sql_generator.py` calls Ollama through LlamaIndex’s Ollama integration. `sql_safety.py` parses SQL, blocks writes, checks tables and columns, and adds a row limit. `query_executor.py` runs approved SQL through SQLAlchemy. `response_formatter.py` creates a basic result explanation. The tests focus on deterministic behavior that should work even when Ollama is unavailable.

## Choosing a local model

| Computer | Starting choice | Trade-off |
|---|---|---|
| 8 GB RAM, CPU-only | Current Qwen 4B-class model | Fastest and lightest; complex joins may be less accurate |
| 16 GB RAM or modest GPU | Qwen2.5-Coder 7B | Recommended balance of SQL ability and speed |
| More memory and slower responses acceptable | Qwen2.5-Coder 14B | Potentially better reasoning; larger download and higher latency |

There is no universal best model. Test three to five questions on the databases you actually use. Keep the schema context compact and avoid sending full table contents to the model.

## Safety design

Generated SQL is untrusted text. The application permits only one parsed `SELECT`, rejects destructive operations such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `ATTACH`, and `DETACH`, checks referenced objects against the discovered schema, limits returned rows, and revalidates every repaired query. If a query fails, the application allows at most two correction attempts.

This is a local prototype, not a complete sandbox for hostile database files. Do not open untrusted databases on a sensitive machine without additional process isolation.

## Test

```bash
pytest -q
```

The tests create an in-memory SQLite database and verify schema discovery, foreign-key detection, safe SELECT handling, destructive-query rejection, unknown-table rejection, and result conversion.

## Troubleshooting

If Streamlit starts but questions fail, check that Ollama is running with `ollama list` and that `OLLAMA_MODEL` matches an installed model. If responses are too slow, select a 4B model, reduce `MAX_ROWS`, and keep uploaded schemas small. If a database fails to load, verify that it is a readable SQLite database rather than a CSV renamed with a database extension.

## Official references

[1]: https://ollama.com/library "Ollama model library"
[2]: https://docs.llamaindex.ai/ "LlamaIndex documentation"
[3]: https://docs.sqlalchemy.org/ "SQLAlchemy documentation"
[4]: https://docs.streamlit.io/ "Streamlit documentation"
[5]: https://docs.pydantic.dev/ "Pydantic documentation"
[6]: https://sqlglot.com/ "SQLGlot documentation"

## Next steps

After the first version works, consider PostgreSQL support, better schema descriptions, query cancellation, stronger isolation, and a benchmark set. Do not add those components before the SQLite workflow is reliable.
