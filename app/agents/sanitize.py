"""Basic prompt-injection defenses for raw user query text (spec Section 10).

No purely textual filter is a complete defense against prompt injection —
this is deliberately the "basic," cheap measure the governing spec commits
to for Phase 1: strip common role/delimiter markers a malicious query might
use to imitate a system-level instruction or a fenced instruction block, and
bound the length so a single query can't blow up prompt size/cost. It does
not attempt semantic detection (e.g. "ignore previous instructions" phrased
in plain English) — that's a different, much harder problem explicitly out
of scope for a "basic" measure.
"""

import re

# Matches every other bounded free-text field in app/agents/models.py
# (AgentError.message, *Response.summary/answer/rationale all cap at 1000) —
# a query can reasonably be longer than a single response field, but still
# bounded, not unlimited.
MAX_QUERY_LENGTH = 2000

# Markers commonly used to imitate a system/role boundary or a fenced
# instruction block within otherwise-plain user content.
_DELIMITER_PATTERNS = [
    re.compile(r"<\|.*?\|>"),  # e.g. <|system|>, <|im_start|>
    re.compile(r"`{3,}"),  # code-fence delimiters
    re.compile(r"(?im)^\s*(system|assistant|developer)\s*:\s*"),  # role prefixes at line start
]


def sanitize_query(raw_query: str) -> str:
    """Strip common injection delimiters and cap length on raw user input.

    Applied once, at the coordinator's single entry point
    (``coordinator.handle_query``), so every downstream use of the same
    query text (the coordinator's own classification prompt, and the text
    reused verbatim as ``RecommendationRequest.query`` /
    ``PolicyRequest.question``) is already sanitized — no per-sub-agent
    call site needs to remember to do this separately.
    """

    query = raw_query
    for pattern in _DELIMITER_PATTERNS:
        query = pattern.sub(" ", query)
    query = " ".join(query.split())  # collapse whitespace/newlines
    return query[:MAX_QUERY_LENGTH]
