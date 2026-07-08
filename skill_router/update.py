"""Авто-обновление каталога: тянет ассеты из последнего GitHub Release в кэш-папку.

Канал распространения — GitHub Releases. Мейнтейнер доливает скиллы → пересобирает
каталог → публикует релиз. Пользователь: `skill-router update` — качает свежий
catalog.jsonl / catalog.db / semantic.npy. VERSION сравнивается, чтобы не качать зря.
"""
import io
import json
import urllib.request
import urllib.error

from . import config

API = "https://api.github.com/repos/{repo}/releases/latest"


def _get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "claude-skill-router"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url, dest, on_progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": "claude-skill-router"})
    with urllib.request.urlopen(req, timeout=120) as r:
        total = int(r.headers.get("Content-Length", 0))
        tmp = dest.with_suffix(dest.suffix + ".part")
        got = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if on_progress and total:
                    on_progress(dest.name, got, total)
        tmp.replace(dest)


def latest_version(repo=None):
    repo = repo or config.CATALOG_REPO
    try:
        rel = _get_json(API.format(repo=repo))
        return rel.get("tag_name") or rel.get("name"), rel
    except urllib.error.HTTPError as e:
        return None, {"error": f"HTTP {e.code}"}
    except Exception as e:
        return None, {"error": str(e)}


def local_version():
    p = config.version_path()
    return io.open(p, encoding="utf-8").read().strip() if p.exists() else None


def update(repo=None, force=False, log=print):
    """Скачать ассеты последнего релиза, если версия новее локальной (или force)."""
    repo = repo or config.CATALOG_REPO
    tag, rel = latest_version(repo)
    if not tag:
        log(f"не удалось получить релиз из {repo}: {rel.get('error')}")
        return False
    cur = local_version()
    if cur == tag and not force:
        log(f"уже актуально: {cur}")
        return True
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    need = [n for n in config.CATALOG_ASSETS if n != "VERSION"]
    missing = [n for n in need if n not in assets]
    if missing:
        log(f"в релизе {tag} нет ассетов: {', '.join(missing)}")
        return False
    dd = config.data_dir()

    def prog(name, got, total):
        log(f"  {name}: {got * 100 // total}%", end="\r")

    for name in need:
        log(f"качаю {name} …")
        _download(assets[name], dd / name, on_progress=prog)
    io.open(config.version_path(), "w", encoding="utf-8").write(tag)
    log(f"готово: каталог обновлён до {tag}")
    return True
