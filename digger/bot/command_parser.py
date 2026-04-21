"""
Command parser — turn a raw @digger mention into a structured search command.

Two intents:
  1. company_search — find contact info for ONE specific named business
     e.g. "find contact info for Acme Coffee in Atlanta"
  2. area_search — find ALL businesses of a category in an area
     e.g. "find all pizza places within 10 miles of downtown Athens GA"

Output is a Command dict consumed by runner.build_prospect_search_args().

Uses Claude (Anthropic SDK) with a forced tool-call to guarantee structured output.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic

log = logging.getLogger(__name__)

_DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

_MENTION_RE = re.compile(r"<@[UW][A-Z0-9]+>\s*", re.IGNORECASE)


@dataclass
class Command:
    intent: str                          # "company_search" | "area_search"
    keywords: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    company_name: str | None = None      # populated only for company_search
    human_summary: str = ""              # one-line summary for the Slack ack

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "keywords": self.keywords,
            "areas": self.areas,
            "company_name": self.company_name,
            "human_summary": self.human_summary,
        }


_SYSTEM = """You parse short business-research requests into structured commands for a prospect-search pipeline.

The pipeline takes TWO inputs:
  - keywords: category terms used to match businesses (e.g. "pizza,pizzeria")
  - areas: geographic strings used as Google Places text queries (e.g. "Athens GA")

Your job is to classify the request into one of two intents and extract those inputs.

INTENTS
=======

1. company_search — user named ONE specific business and wants its contact info.
   Examples:
     "find contact info for Acme Coffee in Atlanta"
     "look up Sal's Pizza in Athens GA"
     "get emails for Urban Grind in Decatur"
   For company_search:
     - company_name = the business name exactly as given
     - keywords = [the company name]  (used as the search query)
     - areas = [the location as stated, e.g. "Atlanta GA"]

2. area_search — user wants ALL businesses of some category in some place.
   Examples:
     "find all pizza places within 10 miles of downtown Athens GA"
     "coffee shops in the Atlanta metro area"
     "bakeries in Roswell GA and Alpharetta"
   For area_search:
     - company_name = null
     - keywords = expanded synonyms for the category. Include the singular form
       AND common variants. E.g. "pizza" → ["pizza","pizzeria"], "coffee" →
       ["coffee","coffee shop","cafe"], "bakery" → ["bakery","bakeshop"],
       "restaurant" → ["restaurant"]. Keep to 1-4 terms; don't over-expand.
     - areas = explicit cities. If user says "metro", "area", "surrounding",
       or "within N miles of X", expand to 3-8 nearby towns/neighborhoods.
       Always include the US state suffix (e.g. "Athens GA" not "Athens").
       If a single specific city is given, return just that one area.

HUMAN_SUMMARY
=============
One-line plain-English confirmation of what you understood, <= 90 chars.
Will be shown to the user as the first Slack message.
Examples:
  "Searching for pizza/pizzeria in Athens GA and 5 nearby towns."
  "Looking up Acme Coffee in Atlanta GA."

RULES
=====
- Always call the `parse_request` tool. Never reply with free text.
- If the request is ambiguous or doesn't match either intent, set intent to
  "unclear" and put the reason in human_summary.
- Never invent a location the user didn't reference."""


_TOOL_SCHEMA = {
    "name": "parse_request",
    "description": "Emit the structured parse of the user's request.",
    "input_schema": {
        "type": "object",
        "required": ["intent", "keywords", "areas", "human_summary"],
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["company_search", "area_search", "unclear"],
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Category terms or company name as search keywords.",
            },
            "areas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "City/town strings with US state suffix.",
            },
            "company_name": {
                "type": ["string", "null"],
                "description": "Only for company_search; otherwise null.",
            },
            "human_summary": {
                "type": "string",
                "description": "<= 90 char confirmation of what you understood.",
            },
        },
    },
}


def strip_mention(text: str) -> str:
    """Remove leading <@UXXXX> Slack user mentions."""
    return _MENTION_RE.sub("", text).strip()


class CommandParseError(Exception):
    pass


def parse(text: str, *, client: Anthropic | None = None, model: str | None = None) -> Command:
    """Parse a raw Slack message body into a Command.

    Raises CommandParseError if the model can't produce a valid parse.
    """
    cleaned = strip_mention(text)
    if not cleaned:
        raise CommandParseError("Empty message after stripping mention.")

    client = client or Anthropic()
    model = model or _DEFAULT_MODEL

    log.info("Parsing command: %r (model=%s)", cleaned, model)

    resp = client.messages.create(
        model=model,
        max_tokens=512,
        system=_SYSTEM,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "parse_request"},
        messages=[{"role": "user", "content": cleaned}],
    )

    # Find the tool_use block.
    tool_block = next(
        (b for b in resp.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_block is None:
        raise CommandParseError(f"Model did not call parse_request. Response: {resp}")

    data = tool_block.input
    if not isinstance(data, dict):
        raise CommandParseError(f"tool_use.input was not a dict: {data!r}")

    intent = data.get("intent")
    if intent not in {"company_search", "area_search", "unclear"}:
        raise CommandParseError(f"Unknown intent: {intent!r}")

    if intent == "unclear":
        # Bubble up with the model's explanation for Slack to render.
        msg = data.get("human_summary") or "Couldn't understand the request."
        raise CommandParseError(msg)

    keywords = [s.strip() for s in (data.get("keywords") or []) if s and s.strip()]
    areas = [s.strip() for s in (data.get("areas") or []) if s and s.strip()]

    if not keywords:
        raise CommandParseError("Parser returned no keywords.")
    if not areas:
        raise CommandParseError("Parser returned no areas.")

    return Command(
        intent=intent,
        keywords=keywords,
        areas=areas,
        company_name=(data.get("company_name") or None) if intent == "company_search" else None,
        human_summary=(data.get("human_summary") or "").strip(),
    )


if __name__ == "__main__":
    # Quick manual test: `python command_parser.py "find all pizza places in athens ga"`
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if len(sys.argv) < 2:
        print("usage: command_parser.py <mention text>", file=sys.stderr)
        sys.exit(2)
    cmd = parse(" ".join(sys.argv[1:]))
    print(json.dumps(cmd.to_dict(), indent=2))
