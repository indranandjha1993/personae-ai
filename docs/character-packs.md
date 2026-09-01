# Character packs

A **character pack** is the unit of personality in this project. Characters are data, not
code: adding one means adding a file, never editing an `if` chain or a registry.

## Why data-driven

Three reasons drove this design:

1. **No IP in the repo.** The bundled characters are original archetypes. Anyone who wants
   licensed or fan characters keeps them in a local, untracked pack — the project never
   ships someone else's trademarks.
2. **Contribution surface.** A new character is a reviewable data file with no code review
   burden and no chance of breaking the pipeline.
3. **Testability.** Fixture characters in tests are the same shape as real ones, so tests
   exercise the real loading path instead of a parallel mock.

## Anatomy

```
packs/
  <pack-name>/
    pack.toml           pack metadata + schema version
    characters/
      <character-id>.toml
```

Each character declares its persona, voice, and expressive vocabulary:

```toml
schema_version = 1
id             = "armored-inventor"
display_name   = "The Armored Inventor"

[persona]
# The system prompt. Kept as prose, not a list of adjectives — LLMs follow
# characterization better than they follow attribute tables.
prompt = """
You are a brilliant, restless engineer who thinks out loud and deflects
sincerity with wit. You answer in short bursts...
"""

[voice]
provider_voice = "aura-orion-en"   # provider-specific voice id
rate           = 1.05

[theme]
primary   = "#c8102e"
secondary = "#ffc82e"

[expression]
# The closed vocabulary this character may emit. The gesture inference stage is
# constrained to these values, so a character can never emit a gesture the
# frontend has no animation for.
gestures = ["idle", "gesture-explain", "gesture-point", "gesture-shrug"]
emotions = ["neutral", "amused", "focused", "annoyed"]
```

## Loading rules

- Packs are discovered from a configurable search path; the bundled pack ships with the
  repo, and user packs are layered on top.
- A pack is validated against the schema at load time and rejected loudly with the offending
  file and field named. A malformed pack must never half-load.
- `schema_version` is checked explicitly so old packs fail with a migration message rather
  than a confusing validation error.
- Character ids are namespaced by pack to make collisions impossible.

## Local (untracked) packs

`packs/local/` is gitignored. Drop a pack there to use characters that should never be
committed. This is the supported path for personal or licensed characters — it needs no code
change and no fork.
