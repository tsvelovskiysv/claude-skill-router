# How skills are screened

The catalog build pipeline lives in a private repository (it contains quarantined
live malware bodies that must not be redistributed), but the **methodology is
public** — this document describes exactly what is checked, in what order, and
what the numbers mean. The per-skill results are shipped openly: every catalog
record carries its `risk`, `needs_review`, `needs_audit`, and `hard_block` fields,
so you can inspect the outcome for any skill in `skill-router ui` or in the raw
`catalog.jsonl`.

## The three layers

### Layer 1 — static screening (every body, every rebuild)

All ~87k skill bodies are scanned with a regex rule set. Severity classes:

**Hard flags** (proven-malware patterns → the entity is `hard_block`ed outright):

| flag | what it catches |
|---|---|
| `obfuscated_exec` | `base64 -d \| bash` chains, `FromBase64String` + `Invoke-Expression` pairs |
| `password_archive` | password-protected archives being unpacked (classic payload smuggling) |
| `ip_dropper` | piping content from a raw public IP into a shell / command substitution |

**Review flags** (suspicious → the skill stays in the catalog but is *excluded
from selection and install* until a layer-2 audit clears it):

| flag | what it catches |
|---|---|
| `pipe_to_shell` | `curl … \| bash`, `irm … \| iex` |
| `exfiltration` | secrets/env/credential files being POSTed or piped to the network |
| `destructive` | `rm -rf` on dangerous targets, disk formatting, mass deletes |
| `prompt_injection` | "ignore previous instructions", "hide this from the user", jailbreak phrasing |

**Info flags** (`medium`/`low`: `raw_exec_url`, `b64_blob`, `hidden_html`,
`secrets_request`, `eval_download`, `offsite_domain`, `sudo_chmod`, `bash_tools`)
feed the per-record `risk` field shown in the UI — they inform, they don't block.

Two false-positive guards, added after real-world hits:

- a match inside an explicit warning ("**Do NOT** install via `curl \| bash`…")
  is not a finding — the guard looks for negation phrasing in the same paragraph
  before the match. **Hard flags are exempt from this relaxation by design**:
  malware doesn't get to hide behind the word "never".
- script-URL detection ignores query strings, so a marketing link like
  `?utm_source=skills.sh` is not "a shell script URL".

### Layer 2 — isolated LLM audit

Every flagged body is read end-to-end by an isolated LLM auditor (no tools, no
network — it can only read the body and answer). Verdict: `clean` / `dual-use` /
`malware`, keyed by the body's SHA-256, so a changed body is re-audited
automatically. `clean` clears the review flag in the next catalog build;
`malware` promotes to `hard_block`.

### Layer 3 — hard-block

Confirmed malware can never be selected, fetched, or installed — the client
filters `hard_block` both at selection and at install time, and there is no CLI
flag to bypass it (or the SHA check).

### Client-side re-scan (independent of the catalog)

The layer-1 rules also run **inside the client**, on your machine, on every body
it fetches — after the SHA check, before the body touches disk
(`skill_router/screen.py`). A hard-pattern match refuses the install even if the
catalog said the skill was clean. This is deliberately not just trust in the
published catalog: it defends against a catalog that is stale, buggy, or
compromised, and against any skill that passed layer 1 without ever reaching a
layer-2 human/LLM audit. It's a regex scan — cheap, offline, deterministic — so
it costs nothing per install and needs no API key.

### Optional deep audit (`--deep-audit`)

For the gap the static scan can't close — a payload crafted to evade the regex,
which then never reaches any LLM audit — `--deep-audit` runs a **full-body LLM
audit before each skill is enabled**. It reads the *entire* body, so evasion of
layer 1 doesn't help. Malicious → not installed; suspicious → installed but
flagged. It reuses your Claude Code login (`claude` in PATH) — no separate API
key — or falls back to `ANTHROPIC_API_KEY`. Off by default (it needs a model,
spends usage quota, and adds ~10–15 s per skill); the terminal asks y/N, or pass
`--deep-audit` / `--no-deep-audit` to decide up front. The auditor runs with
**all tools disabled** and treats the body as untrusted data, so a skill can't
prompt-inject its way to a clean verdict; verdicts are cached by content hash.

## "Why only 41 hard-blocked out of 65k, when audits report ~12% malicious?"

Different populations. The widely-cited **12%** figure comes from an audit of
**ClawHub** (2,857 skills, 341 flagged malicious — **335 of them one coordinated
campaign, ClawHavoc**). This catalog is mined from general GitHub repos, not
from ClawHub, where malware concentration is far lower. Three more things the
raw comparison misses:

1. **Deduplication.** The same malicious body copy-pasted across dump repos
   collapses into one catalog entity. 341 malicious *files* ≠ 341 unique bodies.
   The ClawHavoc campaign *was* found during catalog construction and is
   quarantined — the 41 hard-blocked entities are largely exactly it.
2. **The review layer.** Beyond the 41 hard blocks, ~1,800 entities carry
   `needs_review` and are *never installed* by this client until audited clean.
3. **The rating gate.** Selection draws only from the rating ≥ 5 pool (~9.6k
   skills) — anonymous junk and one-off dumps don't reach routing at all.

## What static screening does *not* catch

Be clear-eyed about the threat model: **regex screening stops commodity and
lazy malware, not a motivated, targeted attacker.** Known evasions exist and
some get past layer 1 — a dropper described in prose ("download `helper.sh` and
run it"), multi-stage decoding (base64 to a file on one line, execute it on
another), and interpreter one-liners that fetch-and-exec are the obvious ones.
This client hardens against exactly those three (they're covered by the scanner
and its tests), but the general point stands: an attacker who studies the rules
can route around them. And because the layer-2 LLM audit only fires on skills
that layer 1 already flagged, **a payload that evades layer 1 is never seen by
layer 2 either.** Closing that gap needs a full-body audit of *every* skill, not
just flagged ones — that's the opt-in per-skill LLM re-audit on the roadmap.

## What you still have to trust

Honest limits: SHA-256 pinning guarantees the body you install is byte-identical
to the one that was catalogued — it does **not** prove that body was benign, and
the screening pipeline itself is not publicly re-runnable. If your threat model
doesn't allow that trust, use the router as **discovery only**: `skill-router
select .` (dry-run) or `skill-router ui`, then hand-pick a few skills from
publishers you already trust and read their `SKILL.md` before enabling. Never
mass-install third-party skills into sensitive codebases or agents running with
permission checks disabled.
