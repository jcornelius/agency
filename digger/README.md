# digger

Prospect-research bot that Slack users invoke with `@digger ...` mentions.

## Layout

    bot/         — Slack Socket Mode bot (orchestration layer)
    scripts/     — Pipeline scripts (Brave + Google Places → HubSpot → Hunter.io)
    briefs/      — Keyword matching rules consumed by the pipeline
    research/    — CSV output from past runs (audit trail)
    docs/        — Reference material (Hubspot property guide, strategic criteria)

## Getting started

See `bot/README.md` for the full setup + operation guide, or just run:

    bash bot/finish-setup.sh

once `bot/.env` is populated with your API keys.

## External dependency

The pipeline shells out to `goplaces` (Google Places CLI) for place lookups.
It must already be installed on this machine. Verify with:

    which goplaces

If it's missing, install it however you originally installed it on the
OpenClaw setup — the binary travels with the machine, not the codebase.
