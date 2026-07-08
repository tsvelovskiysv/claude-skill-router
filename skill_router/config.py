"""Пути и настройки — кроссплатформенно, без хардкода.

Данные каталога (catalog.jsonl / semantic.npy) живут в кэш-папке
пользователя, а не в репо (они тяжёлые и генерируемые). Скачиваются командой
`skill-router update` из GitHub Release. Переопределить папку: env
CLAUDE_SKILL_ROUTER_DATA.
"""
import os
import sys
from pathlib import Path

# репозиторий-источник каталога (Release-ассеты). Меняется на реальный при публикации.
CATALOG_REPO = os.environ.get("CLAUDE_SKILL_ROUTER_REPO", "tsvelovskiysv/claude-skill-router")
CATALOG_ASSETS = ("catalog.jsonl", "semantic.npy", "semantic_ids.json", "VERSION")


def data_dir() -> Path:
    """Папка с данными каталога. Env override → иначе кроссплатформенный кэш пользователя."""
    env = os.environ.get("CLAUDE_SKILL_ROUTER_DATA")
    if env:
        d = Path(env)
        d.mkdir(parents=True, exist_ok=True)
        return d
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    d = base / "claude-skill-router"
    d.mkdir(parents=True, exist_ok=True)
    return d


def catalog_path() -> Path:
    return data_dir() / "catalog.jsonl"


def semantic_path() -> Path:
    return data_dir() / "semantic.npy"


def semantic_ids_path() -> Path:
    return data_dir() / "semantic_ids.json"


def version_path() -> Path:
    return data_dir() / "VERSION"


def data_ready() -> bool:
    """Есть ли минимум для работы (каталог метаданных)."""
    return catalog_path().exists()


def semantic_ready() -> bool:
    return semantic_path().exists() and semantic_ids_path().exists()
