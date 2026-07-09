# Security

Skills are executable instructions. Public skill catalogs contain malware. This
project is designed so that it **does not redistribute untrusted code** and known
malware is never installed through it.

## What the shipped catalog contains

Metadata and embeddings only — names, descriptions, ratings, categories, tags,
canon repo + path, SHA-256 hashes, vectors. **No skill bodies are ever shipped.**

## Three layers

1. **Static screening** — every skill body was scanned for malware patterns
   (obfuscated `base64`→`exec`, password-protected archives, IP/payload droppers).
   Matches are flagged `needs_review`.
2. **Isolated LLM audit** — flagged bodies get an isolated, read-only LLM audit
   before they can be recommended. Verdict `clean|dual-use|malware`.
3. **Hard-block** — confirmed malware is hard-blocked and can never be selected,
   fetched, or installed. 41 skills are currently hard-blocked. Real malware was
   found during catalog construction (e.g. ClawHavoc, which embedded C2 server
   addresses in skill bodies).

## Install-time guarantees

- `hard_block` skills are never fetched or installed.
- `needs_review` / `needs_audit` skills are excluded from selection and never installed.
- Bodies are fetched **from the origin GitHub repo** and verified against the
  catalog's stored SHA-256. If the origin changed since cataloguing, the SHA
  mismatches and the install is skipped. A catalog record without a SHA is
  skipped too (fail-closed). There is no CLI flag to bypass verification.
- Skill names and package paths are validated against path traversal
  (including Windows reserved names).
- The `ui` dashboard binds to `127.0.0.1` only and validates the `Host` header
  against DNS rebinding.

## Supported versions

Only the latest release receives security fixes. The catalog itself updates
independently of the client via `skill-router update`.

## Reporting

Found a malicious skill that slipped through, or a security issue in the tool?
Open a **private security advisory**:
[Security → Advisories → Report a vulnerability](https://github.com/tsvelovskiysv/claude-skill-router/security/advisories/new).
Do not file a public issue with a working exploit payload.

You can expect an initial response within **7 days**. Confirmed malicious skills
are hard-blocked in the next catalog release.
