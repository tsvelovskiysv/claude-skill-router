"""Установка скиллов: тело качается из ИСТОЧНИКА (GitHub) на лету, а не из склада.

Безопасность: (1) hard_block (malware) не ставится; (2) SHA-256 тела сверяется с каталогом
— несовпадение ИЛИ отсутствие sha в каталоге → пропуск (fail-closed, неаудированное тело
не ставим); (3) имя скилла и пути пакета валидируются от path-traversal. Тела нигде не
тиражируются — берутся из первоисточника, поэтому вредонос не распространяется.
"""
import os
import io
import re
import json
import time
import base64
import hashlib
import urllib.request
import urllib.error

CONTENTS_API = "https://api.github.com/repos/{repo}/contents/{path}"
_BAD_NAME = re.compile(r'[\\/:*?"<>|]')
# зарезервированные имена Windows: CON/NUL/COM1… как папка → необработанный OSError
_WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)


def _safe_name(name):
    n = (name or "").strip()
    if not n or n.startswith(".") or _BAD_NAME.search(n) or len(n) > 80:
        return None
    if _WIN_RESERVED.match(n) or n.endswith((".", " ")):
        return None
    return n


def _gh_get(url, token=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "claude-skill-router"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def rate_status(token=None):
    """Остаток квоты GitHub API → (remaining, limit, reset_epoch) или None.
    Сам запрос /rate_limit квоту не тратит — безопасно для pre-flight проверки."""
    try:
        d = _gh_get("https://api.github.com/rate_limit", token)
        core = (d.get("resources") or {}).get("core") or {}
        return core.get("remaining"), core.get("limit"), core.get("reset")
    except Exception:
        return None


def fetch_body(canon, canon_path, token=None):
    """SKILL.md из репо-источника (default branch) → (bytes|None, http_code|None)."""
    if not canon or not canon_path:
        return None, None
    url = CONTENTS_API.format(repo=canon, path=canon_path.lstrip("/"))
    try:
        d = _gh_get(url, token)
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, None
    if isinstance(d, dict) and d.get("encoding") == "base64" and d.get("content"):
        try:
            return base64.b64decode(d["content"]), None
        except Exception:
            return None, None
    return None, None


def install(project, selection, base_names=None, token=None, allow_changed=False, log=print):
    """selection = list[dict] (из select.select). Ставит чистые в <project>/.claude/skills/."""
    base_names = set(n.lower() for n in (base_names or []))
    skills_dir = os.path.join(project, ".claude", "skills")
    os.makedirs(skills_dir, exist_ok=True)
    root = os.path.normpath(skills_dir)

    installed, blocked, changed, invalid, flagged, failed, no_sha = [], [], [], [], [], [], []
    rate_limited = False
    for it in selection:
        name = _safe_name(it.get("name"))
        if not name:
            invalid.append(repr(it.get("name"))); continue
        if it.get("hard_block"):
            blocked.append(name); continue
        if it.get("needs_review") or it.get("needs_audit"):
            flagged.append(name); continue           # флагнутые — только после аудита (см. README)

        cat_sha = it.get("sha256")
        if not cat_sha and not allow_changed:
            no_sha.append(name); continue            # без sha верифицировать нечем — fail-closed

        body, code = fetch_body(it.get("canon"), it.get("canon_path"), token)
        if not body:
            if code in (403, 429):
                rate_limited = True
            failed.append(name); continue

        real_sha = hashlib.sha256(body).hexdigest()
        if cat_sha and real_sha != cat_sha and not allow_changed:
            changed.append(name); continue           # тело изменилось с момента аудита

        dest = os.path.normpath(os.path.join(skills_dir, name))
        if not (dest == root or dest.startswith(root + os.sep)):
            invalid.append(name); continue
        os.makedirs(dest, exist_ok=True)
        with open(os.path.join(dest, "SKILL.md"), "wb") as f:
            f.write(body)
        installed.append(name)

    # settings.json: обновляем только skillOverrides, чужое сохраняем
    settings_path = os.path.join(project, ".claude", "settings.json")
    existing = {}
    if os.path.exists(settings_path):
        try:
            existing = json.loads(io.open(settings_path, encoding="utf-8").read())
            if not isinstance(existing, dict):
                raise ValueError
        except Exception:
            bak = settings_path + ".bak." + time.strftime("%Y%m%d_%H%M%S")
            os.replace(settings_path, bak)
            log(f"settings.json was invalid JSON — the original is saved as {os.path.basename(bak)}")
            existing = {}
    overrides = dict(existing.get("skillOverrides") or {})
    for n in installed:
        overrides[n] = "on" if n.lower() in base_names else "name-only"
    existing["skillOverrides"] = overrides
    existing["_skill_router"] = "manages only skillOverrides"
    io.open(settings_path, "w", encoding="utf-8").write(json.dumps(existing, ensure_ascii=False, indent=2))

    return {"installed": installed, "blocked": blocked, "changed": changed,
            "invalid": invalid, "flagged": flagged, "failed": failed,
            "no_sha": no_sha, "rate_limited": rate_limited}
