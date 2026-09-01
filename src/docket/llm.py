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


def get_chat_model(*, temperature: float = 0.0) -> ChatGroq:
    """Build the Groq chat client from GROQ_API_KEY / GROQ_MODEL.

    Reads from process environment, populated by `load_dotenv()` above from
    a `.env` file at the repo root (gitignored; see `.env.example`).
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Create a .env file at the repo root "
            "with GROQ_API_KEY=... (see .env.example)."
        )
    model_name = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    return ChatGroq(model=model_name, api_key=SecretStr(api_key), temperature=temperature)
