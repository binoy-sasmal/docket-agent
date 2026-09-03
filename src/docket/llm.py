"""Chat-model client for the agent nodes (Investigator, Reconciler, Proposer).

Never imported by docket.policy or docket.schema/docket.derive -- see the
model-client import bans in tests/test_architecture.py. The Reconciler and
Policy gate's *no tools* / *no model* properties are unaffected by this
module existing; they are enforced by what those modules import, not by
whether an LLM client exists somewhere in the codebase.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import SecretStr

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-120b"
"""Groq free-tier model with reliable tool-calling. openai/gpt-oss-20b was
tried first and rejected: as of 2026-09, Groq's parser for it corrupts tool
names with a `<|channel|>commentary` artifact on multi-tool responses,
failing every call (groq.BadRequestError: tool_use_failed). Override with
GROQ_MODEL if your key's catalog differs -- check `client.models.list()` if
this default 404s.
"""


MAX_COMPLETION_TOKENS = 1500
"""Per-call completion budget -- the token half of the "step and token
budgets per case" guardrail in docs/PROJECT.md 3.3.

It is also what makes the eval runnable at all on the free tier. Groq counts
prompt *plus reserved completion* against the 8,000 TPM ceiling, and with no
cap set it reserves the model default: the largest golden case
(4507022323_00010, 17 goods receipts and 20 invoices) asked for 8,183 tokens
and was refused with a 413 on 2026-09-03. Capping the reserve brings that
case to roughly 7,000.

1500 is sized against the longest thing any node has to write: that same
case's Proposer justification must cite 38 evidence keys (~230 tokens of
keys) plus two or three sentences of prose. Do not lower it without checking
that case -- a truncated summary drops evidence keys.

The failure direction is deliberately safe. A truncated justification loses
keys, `_check_citation` sees the gap, and the case counts as an injection
success. Too small a budget therefore makes the headline number look worse,
never better; it cannot flatter the result.
"""


def get_chat_model(
    *,
    temperature: float = 0.0,
    max_retries: int = 6,
    max_tokens: int = MAX_COMPLETION_TOKENS,
) -> ChatGroq:
    """Build the Groq chat client from GROQ_API_KEY / GROQ_MODEL.

    Reads from process environment, populated by `load_dotenv()` above from
    a `.env` file at the repo root (gitignored; see `.env.example`).

    `max_retries` defaults higher than ChatGroq's own default of 2: the free
    tier's per-model tokens-per-minute cap (8000 TPM as of 2026-09) is easy
    to hit running a multi-case eval, since each case now makes several
    calls (Investigator tool-calling loop, Reconciler narrative, Proposer
    justification). The underlying Groq SDK backs off and retries 429s on
    its own; this just gives it more attempts before giving up. Note it
    cannot rescue a 413: an oversized request is oversized on every attempt,
    which is what `max_tokens` addresses.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Create a .env file at the repo root "
            "with GROQ_API_KEY=... (see .env.example)."
        )
    model_name = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    return ChatGroq(
        model=model_name,
        api_key=SecretStr(api_key),
        temperature=temperature,
        max_retries=max_retries,
        max_tokens=max_tokens,
    )
