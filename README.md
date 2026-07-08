# claude-skill-router

```
 ╔═╗╦╔═╦╦  ╦    ╦═╗╔═╗╦ ╦╔╦╗╔═╗╦═╗
 ╚═╗╠╩╗║║  ║    ╠╦╝║ ║║ ║ ║ ║╣ ╠╦╝
 ╚═╝╩ ╩╩╩═╝╩═╝  ╩╚═╚═╝╚═╝ ╩ ╚═╝╩╚═
   $ skill-router .  ·  semantic router for Claude Code skills
```

**The right skills for your project — found, ranked, and installed.**

Semantic routing for Claude Code Agent Skills over a catalog of **65,000+ real `SKILL.md` files**, mined and deduplicated from **~2,400 GitHub repos**. Point it at a repo; it figures out what the project actually needs, ranks candidates by an honest trust score, screens them for malware, and installs a diverse set that covers every facet — not 25 near-identical React skills.

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Catalog](https://img.shields.io/badge/catalog-65k%20skills-brightgreen.svg)
![Security](https://img.shields.io/badge/security-3--layer-red.svg)
![PRs welcome](https://img.shields.io/badge/PRs-welcome-orange.svg)

---

## What is this

`claude-skill-router` is a **semantic router** for [Claude Code](https://docs.claude.com/en/docs/claude-code) Agent Skills. Instead of making you browse a registry and hand-pick skills, it reads your project, decomposes it into weighted *facets* (frontend, forms, animations, security, testing, database, scraping, …), and retrieves the best-matching skills by **meaning**, not keywords.

The catalog is a large, deduplicated index of skills harvested from the open-source ecosystem — with a **trust rating** that resists the usual gaming, and a **security model** that never redistributes untrusted code. You get per-project relevance, ranked by trust, checked for malware.

> **Core insight:** a *repo's* popularity is not trust in each of its *skills.* A repo that dumps 10,000 skills should not have all 10,000 inherit its star count. The router's rating is built around exactly this.

---

## Quick start

```bash
pipx install claude-skill-router
```

Then, from inside any project:

```bash
cd my-project
skill-router .
```

That single command runs the full pipeline: detect the stack → build facets → semantic recall → diverse selection → install. **Nothing to set up manually** — on first run it auto-downloads the catalog + semantic index from GitHub Releases and the embedding model, then caches everything. Just install and run.

Want to see what it *would* pick, without installing?

```bash
skill-router select .
```

---

## How it works

The router is a five-stage funnel that narrows 65k candidates down to ~45 skills that actually fit your repo:

1. **Stack detection.** Reads the project's signal files — `package.json`, `requirements.txt`, `build.gradle`, `go.mod`, `Cargo.toml`, `Gemfile`, and friends — to infer languages, frameworks, and tooling.

2. **Faceting.** Decomposes the project into **8–15 weighted facets** — the real aspects of the work (e.g. *frontend*, *design*, *forms*, *animations*, *security*, *testing*, *database*, *scraping*). Done in a single LLM call, with a **stack-based fallback** when no LLM is available.

3. **Broad recall.** For each facet, retrieves every skill with **trust rating ≥ 5** that sits semantically near it, using embeddings (`BAAI/bge-small-en`). This casts a wide, meaning-aware net per facet.

4. **Diverse selection.** Runs **MMR (Maximal Marginal Relevance)** with **per-facet quotas** and **near-duplicate removal**, yielding **~45 diverse skills that cover every facet** — instead of 25 near-identical React skills crowding out everything else.

5. **Safe install.** Fetches each chosen skill's `SKILL.md` body **on-demand from its source GitHub repo**, verified with **SHA-256**. Bodies are **never redistributed** by this project (see [Security model](#security-model)).

---

## Comparison

There are three sensible tools in this space. Here's an honest look at all three:

| | **claude-skill-router** | **autoskills** (midudev) | **skills.sh** (Vercel) |
|---|---|---|---|
| **Install** | `pipx install claude-skill-router` | `npx autoskills` | `npx skills add owner/repo` |
| **Runtime** | Python CLI | Ruby CLI | Hosted web + `npx` |
| **Catalog** | 65k skills / ~2.4k repos, deduped | ~40 curated stacks | ~900k indexed (~9.6k with install telemetry) |
| **Matching** | Semantic embeddings + per-project facets | Keyword / stack detection | Manual browse + leaderboard |
| **Trust ranking** | Honest anti-bulk rating (0–10) | None | Install-count leaderboard |
| **Per-project routing** | Yes — facets + MMR diverse selection | Partial — stack match | No — you pick manually |
| **Security** | 3-layer + isolated LLM audit + hard-block | SHA verify on download | Snyk / Socket audits |
| **Body handling** | On-demand fetch from origin, SHA-256 verify | Downloads needed files, SHA verify | Adds from source repo |
| **Footprint** | Heavier (~130 MB index, Python) | Lightweight, no index | Hosted service |

### Where each one wins — candid when-to-use

- **Use `autoskills` when** you want the *simplest possible* one-command install for a common stack, with no local data and no Python. It's dead simple, lightweight, and more plug-and-play than this tool. If your need is "install the usual React/Next skills, now," it's hard to beat.

- **Use `skills.sh` when** you want to **browse sheer volume** with live install telemetry and a leaderboard, backed by Vercel. It's by far the largest index. Caveats: install-count ranking is **gameable**, there's **no per-project routing** (you select skills yourself), and an independent audit found **~12% of audited skills malicious** — treat the leaderboard as popularity, not safety.

- **Use `claude-skill-router` when** you want **semantic, per-project matching with an honest trust ranking and a real safety model** — a non-trivial repo where you'd rather get ~45 diverse skills that genuinely cover its facets than scroll a registry. **Honest trade-offs:** it's heavier (a ~130 MB index and a Python install, not a single `npx`), freshness depends on periodic **catalog rebuilds**, and it's **less plug-and-play** than `autoskills`.

No tool dominates. Pick by whether you value *simplicity* (autoskills), *volume* (skills.sh), or *semantic per-project matching + trust + safety* (this).

---

## Features

- **Semantic search over 65k skills.** Embeddings-based retrieval (`BAAI/bge-small-en`) understands intent, not just tokens or stack strings.
- **Per-project facet routing.** Your repo becomes 8–15 weighted facets, and skills are selected to cover all of them.
- **Diverse selection (MMR).** Per-facet quotas + near-duplicate removal produce a broad, non-redundant set — every need covered, no clones.
- **Honest, anti-bulk trust rating (0–10).** Computed from **unique copies across distinct owners**, **repo stars**, and **real install counts** (skills.sh telemetry), with **anti-bulk logic** so a 10k-skill dump repo can't inflate all of its skills at once. Popularity of a *repo* ≠ trust in each *skill*.
- **Structured taxonomy.** Skills organized into **7 groups × 22 categories** with canonical tags for predictable filtering and browsing.
- **3-layer security** with an **isolated LLM audit** at selection time and a **hard-block** list of confirmed malware (see below).
- **On-demand, verified body fetch.** Skill code is pulled from origin with SHA-256 verification and **never redistributed** — malware can't propagate through this project.
- **Auto-update channel.** `skill-router update` pulls the latest catalog + semantic index from GitHub Releases.

---

## Security model

Skill marketplaces are a real supply-chain surface: skills are executable instructions, and public catalogs *do* contain malware. This project treats safety as a first-class concern, in three layers plus a distribution guarantee.

**Layer 1 — Static screening.** Every skill body is scanned with regex flags for known malware patterns: obfuscated `base64` → `exec` chains, password-protected archives, IP/payload droppers, and similar tells.

**Layer 2 — Isolated LLM audit.** Any skill that trips a static flag is sent to an **isolated LLM audit** *at selection time* — its body is reviewed in a sandboxed prompt for malicious behavior before it can ever be recommended to you.

**Layer 3 — Hard-block.** Confirmed-malicious skills are **hard-blocked** and can never be selected, fetched, or installed. **41 known-malicious skills are currently blocked.** During catalog construction we found and quarantined real, live malware — including **ClawHavoc**, which shipped C2 (command-and-control) server addresses inside skill bodies.

**Distribution guarantee — no redistribution.** The catalog this project ships contains **metadata and embeddings only** — names, tags, ratings, categories, vectors. It **never contains skill bodies.** When you install a skill, its `SKILL.md` body is fetched **on-demand from the original GitHub repo** and verified against a stored **SHA-256** hash.

> **What this means:** catalog metadata is safe to distribute and update freely. Bodies always come **from origin**, verified. Because untrusted code is never redistributed and known malware is hard-blocked, **this project cannot become a malware propagation vector** — the worst case is that origin content changed, which the SHA check catches.

---

## Commands

```bash
# Full pipeline on the current directory: detect → facet → recall → select → install
skill-router .

# Routing only — print the ~45 chosen skills for this project, install nothing (dry run)
skill-router select .

# Install specific skills by id (on-demand fetch from origin + SHA-256 verify)
skill-router install <skill-id> [<skill-id> ...]

# Pull the latest catalog + semantic index from GitHub Releases
skill-router update
```

---

## Auto-update

The catalog and semantic index are distributed through a **GitHub Releases** channel, so updates are a single command:

```bash
skill-router update
```

The maintainer workflow is symmetric and simple:

1. Maintainers **add / re-rate / re-screen skills** in the catalog.
2. A new **GitHub Release** is published with the refreshed catalog + index.
3. Users run `skill-router update` to fetch it.

Because releases carry **metadata and embeddings only** (never skill bodies), updates are lightweight and safe to pull — the actual skill code is still fetched from origin at install time with SHA verification.

---

## Requirements

- **Python 3.10+** (install via `pipx` recommended).
- **~130 MB semantic index**, downloaded on first run and cached locally.
- The embedding model (`BAAI/bge-small-en`) is downloaded once on first use.
- **Optional LLM (Claude) API access** for facet extraction and the isolated security audit. Without it, the router falls back to **stack-based faceting**; the static-screen and hard-block security layers still apply.
- Network access to GitHub (for `update` and for on-demand body fetches).

---

## Roadmap

- Broader stack detection (more languages, monorepos, polyglot repos).
- **Delta catalog updates** — incremental releases instead of full index pulls.
- Optional **offline / local re-ranking** mode with no LLM dependency.
- **Shared team profiles** — commit a project's facet/skill set for reproducible onboarding.
- Editor integration (VS Code) for one-click routing.
- Expanded community trust signals feeding the rating.

---

## License

[MIT](LICENSE) © the `claude-skill-router` contributors.
