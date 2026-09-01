# Contributing

Thanks for taking an interest. This document covers the conventions that keep the project
coherent.

## Two hard rules

**1. No third-party character intellectual property.** Bundled characters are original
archetypes. Do not submit characters based on Marvel, DC, or any other franchise, and do not
use their names in code, tests, fixtures, or documentation. Licensed or personal characters
belong in `packs/local/`, which is gitignored.

**2. The project must run without API keys.** Providers sit behind interfaces with mock
implementations as the default. Never write a code path — or a test — that fails when no
credentials are present.

## Development setup

```bash
cd apps/backend && uv sync
cd apps/frontend && npm ci
```

No credentials needed. Everything runs on mock providers by default.

### Editor setup

VS Code settings are committed. Open the repository root (not `apps/backend`) and accept the
recommended extensions when prompted; the interpreter, `src` layout, pytest root, and Ruff
configuration are all wired up already.

The virtualenv lives at `apps/backend/.venv`, which editors do not discover on their own --
that is what `python.defaultInterpreterPath` is for. If imports of `personae` show as
unresolved, the interpreter is the first thing to check.

## Working style

**Tests first.** Write a failing test, make it pass, then tidy. Every bug fix needs a
regression test that fails without the fix. Assert on observable behaviour, not on how many
times a mock was called.

**Typing is strict and enforced.** mypy runs in strict mode; TypeScript has no `any` and no
casts used to silence the compiler. Data arriving over the network is untrusted: parse and
narrow it, never cast it into shape. A `# type: ignore` needs a specific error code and a
reason.

**Characters stay data.** Character-specific behaviour goes in a pack file. If you find
yourself writing `if character_id == ...`, the design is wrong.

**Respect the provider boundary.** STT/LLM/TTS are used only through their protocols. A
vendor SDK type appearing in pipeline or domain code breaks the mock path.

## Commits

Conventional Commits, imperative mood, one concern per commit:

```
feat(packs): validate character schema version on load
fix(audio): release worklet node when the session closes
test(pipeline): cover reconnect after transport drop
```

The body explains *why* — the diff already shows what.

## Pull requests

Before opening a PR:

```bash
# Backend
uv run pytest && uv run ruff check . && uv run mypy .

# Frontend
npm test && npm run lint && npm run typecheck
```

CI runs the same checks on Python 3.12 and 3.13. Describe what changed and why; link the
issue if there is one.
