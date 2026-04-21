# TOOLS.md - Local Notes & Tool Efficiency

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

---

## 🔧 Use the Right Tool for the Job

**Rule: If a task can be done with a shell command, use bash. Don't send simple operations to the LLM.**

Your bash tool is your most efficient tool. Use it FIRST for anything that doesn't require reasoning or web access.

### File Operations — Always Use Bash

| Task | Command |
|------|---------|
| Count lines in a file | `wc -l file.csv` |
| Count data rows (skip header) | `tail -n +2 file.csv \| wc -l` |
| Read a file | `cat file.csv` or `head -20 file.csv` |
| Check if file exists | `test -f file.csv && echo yes` |
| Get file size | `ls -lh file.csv` |
| Search within a file | `grep "pattern" file.csv` |
| Sort / extract columns | `sort`, `cut`, `awk` |
| List files | `ls directory/` |
| Find files by pattern | `find . -name "*.csv"` |
| Git operations | `git status`, `git log`, `git diff` |

### When TO Use the LLM

- **Reasoning**: Decisions, prioritization, analysis
- **Writing**: Composing messages, summaries, code
- **Web research**: Finding information, verifying websites
- **Complex logic**: Anything requiring judgment

### The 5-Second Rule

Before sending data to the model, ask: **"Could I answer this with a one-liner in bash?"**
If yes → use bash. If no → use the model.

---

## What Else Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.
