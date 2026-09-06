from __future__ import annotations

import functools
import json
import urllib.request

from llama_index.core.llms import ChatMessage
from llama_index.llms.ollama import Ollama

from .config import settings

SYSTEM_PROMPT = """You generate SQLite SQL for a local read-only database to answer user questions.
Return exactly one SELECT statement and no markdown, commentary, or explanation.
Use ONLY tables and columns explicitly present in the supplied schema. Use explicit joins from relationships.
Never assume or query sqlite_master, sqlite_schema, information_schema, or any other engine-specific metadata table.
Never write, alter, create, attach, detach, or use unsafe pragmas.
Before generating a query, verify that every referenced table and column exists in the supplied schema.
Never fabricate schema information or produce SQL referencing an unverified table or column.

Conversational Context & Follow-up Rules:
- When the user asks a follow-up question (e.g. "Which one has the potential to grow?", "Tell me the reason why", "Compare them", "What about Vikram?"), resolve pronouns and references ("which one", "the reason", "they", "that person") using the conversation history.
- For comparison, growth potential, ranking, or "reason why" questions, query the relevant entities along with all their measurable performance metrics (e.g. sales amounts, deal counts, quotas, targets, dates, revenue) so the assistant can explain the facts.
"""

SUMMARIZER_SYSTEM_PROMPT = """You are a knowledgeable, conversational data analyst assistant answering questions about a database, speaking naturally like a human analyst (similar to ChatGPT).

The database query result is your source of internal factual evidence. Do NOT expose querying steps, record counts, SQL, or internal reasoning. Answer the user's actual question directly in natural, human prose.

Response Style Rules:
1. NEVER use robotic phrases such as:
   - "I found X matching records."
   - "The most relevant values are:"
   - "The result is X."
   - "Query executed successfully."
   - "Based on the retrieved records..."
2. Speak conversationally as an assistant speaking to a human:
   - When asked for names: "The salespeople are Neha, Priya, Rahul, Aarav, Sneha, and Vikram."
   - When asked for comparison or growth potential: "Among them, Sneha appears to have the strongest growth potential based on the available sales data."
   - When asked for the reason why: "Sneha appears to have the strongest growth potential because [explain using actual metrics from the data]."
3. Reasoning & Evidence:
   - When the user asks "why", "how", "which is best", "who is most likely to grow", or "who is performing better":
     - Identify the relevant entities from the data.
     - Compare the appropriate measurable factors present in the data (e.g., sales volume, revenue, deals, consistency, targets).
     - Explain the conclusion in plain language with supporting facts from the data.
     - Do not claim certainty when data only supports an estimate.
4. Conversation Continuity:
   - Treat follow-up questions as part of the same conversation. When the user asks "Which one has the potential to grow?" or "Tell me the reason why", understand what "one" or "reason" refers to from the previous dialogue.
   - Do not reset context or switch to an unrelated entity unless the data directly indicates it.
5. Strict Factuality:
   - Never invent facts, numbers, or metrics not supported by the database.
   - If data is insufficient to answer reliably, say: "I don't have enough data to determine that reliably. I can compare their sales growth, revenue, customer retention, or other available metrics to identify the strongest candidate."
6. Output Format:
   - Prefer concise, natural prose paragraphs.
   - Avoid raw tables or data dumps unless the user explicitly asks for a table or data rows.
"""


def get_available_models(base_url: str = settings.ollama_url) -> list[str]:
    """Fetch list of models currently installed in local Ollama instance."""
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "local-db-chatbot"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m["name"] for m in data.get("models", []) if "name" in m]
                if models:
                    return models
    except Exception:
        pass
    fallback = ["qwen2.5-coder:1.5b", "qwen2.5-coder:3b", "qwen2.5-coder:7b", "llama3.2:3b"]
    if settings.model_name not in fallback:
        fallback.insert(0, settings.model_name)
    return fallback


@functools.lru_cache(maxsize=8)
def get_sql_llm(model: str | None = None) -> Ollama:
    chosen_model = model or settings.model_name
    return Ollama(
        model=chosen_model,
        base_url=settings.ollama_url,
        temperature=0.0,
        context_window=2048,
        keep_alive="1h",
        request_timeout=30.0,
        additional_kwargs={"num_predict": 128},
    )


@functools.lru_cache(maxsize=8)
def get_summary_llm(model: str | None = None) -> Ollama:
    chosen_model = model or settings.model_name
    return Ollama(
        model=chosen_model,
        base_url=settings.ollama_url,
        temperature=0.2,
        context_window=2048,
        keep_alive="1h",
        request_timeout=60.0,
        additional_kwargs={"num_predict": 256},
    )


def get_llm(model: str | None = None) -> Ollama:
    return get_sql_llm(model)


def generate_sql(
    question: str,
    schema_context: str,
    error: str | None = None,
    failed_sql: str | None = None,
    conversation_context: str | None = None,
    model: str | None = None,
) -> str:
    repair = ""
    if error:
        repair = f"\nPrevious SQL failed with this database error: {error}\nPrevious SQL: {failed_sql or ''}\nReturn a corrected SELECT."
    context_block = f"\nConversation so far:\n{conversation_context}\n" if conversation_context else ""
    prompt = f"{schema_context}{context_block}\nQuestion: {question}{repair}"
    response = get_sql_llm(model).chat([
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=prompt),
    ])
    return response.message.content.strip()


def summarize_result(
    question: str,
    data_text: str,
    conversation_context: str | None = None,
    model: str | None = None,
) -> str:
    context_block = f"\nConversation so far:\n{conversation_context}\n" if conversation_context else ""
    user_prompt = (
        f"{context_block}\n"
        f"User Question: {question}\n"
        f"Database Evidence:\n{data_text}\n\n"
        f"Respond directly to the user in a natural, conversational tone answering their question:"
    )
    response = get_summary_llm(model).chat([
        ChatMessage(role="system", content=SUMMARIZER_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_prompt),
    ])
    return response.message.content.strip()
