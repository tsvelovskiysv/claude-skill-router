"""CLI: skill-router [.|select|install|update].

  skill-router .            детект → грани → отбор → установка
  skill-router select .     то же, но без установки (dry-run)
  skill-router install ...  установить конкретные скиллы по имени
  skill-router update       обновить каталог+индекс из GitHub Release
"""
import os
import io
import sys
import json
import time
import argparse

from . import config, stack as stack_mod, facets as facets_mod, ui


def _risk_c(risk):
    return {"high": ui.red, "medium": ui.yellow, "low": ui.gray}.get(risk, ui.gray)(risk or "none")


def _ensure_data():
    """Данных нет → авто-докачка из релиза (первый запуск ставит всё сам)."""
    if config.data_ready() and config.semantic_ready():
        return True
    from . import update as update_mod
    print(ui.dim("First run — downloading catalog + index from GitHub Release …"))
    ok = update_mod.update(force=True)
    if not ok:
        print(ui.yellow("Could not download the catalog. Check network / repo, then retry."),
              file=sys.stderr)
    return ok


def _manifest_text(project):
    """Текст файлов зависимостей — какие продукты проект реально использует."""
    import fnmatch
    pats = ("requirements.txt", "package.json", "pyproject.toml", "go.mod", "Gemfile",
            "composer.json", "Cargo.toml", "pom.xml", "*.lock", "docker-compose*.yml", ".env.example")
    out = []
    for p in stack_mod.iter_files(project):
        base = os.path.basename(p).lower()
        if any(fnmatch.fnmatch(base, pat) for pat in pats):
            try:
                out.append(io.open(p, encoding="utf-8", errors="replace").read()[:20000])
            except Exception:
                pass
            if len(out) >= 40:
                break
    return " ".join(out).lower()


def _check_rate(install_mod, token, needed):
    """Pre-flight: хватит ли квоты GitHub API на установку. → False = ставить нечем."""
    rs = install_mod.rate_status(token)
    if not rs or rs[0] is None:
        return True                                # сеть/эндпоинт недоступны — не гадаем
    remaining, limit, reset = rs
    mins = max(1, int((reset - time.time()) / 60)) if reset else 60
    if remaining == 0:
        print(ui.red(f"GitHub API rate limit exhausted (0/{limit}). ")
              + ui.yellow(f"Resets in ~{mins} min."
                          + ("" if token else " Set GITHUB_TOKEN to get 5000 req/h.")),
              file=sys.stderr)
        return False
    if remaining < needed:
        print(ui.yellow(f"GitHub API: {remaining}/{limit} requests left this hour, "
                        f"{needed} needed — some installs will fail (resets in ~{mins} min)."
                        + ("" if token else " Set GITHUB_TOKEN to get 5000 req/h.")))
    return True


def _load_facets(project, prof, about):
    fp = os.path.join(project, ".claude", "skills-facets.json")
    if os.path.exists(fp):
        try:
            return json.loads(io.open(fp, encoding="utf-8").read()), "LLM"
        except Exception:
            pass
    return facets_mod.from_stack(prof, about), "stack fallback"


def _decide_deep_audit(deep_audit, n):
    """Три ветки: флаг задан → да; живой терминал → спросить; не-TTY → нет."""
    from . import deep_audit as da
    if deep_audit == "off":
        return False
    if not da.available():
        if deep_audit == "on":                       # явно просили, но нечем
            print(ui.yellow("--deep-audit needs Claude Code (`claude` in PATH) or "
                            "ANTHROPIC_API_KEY — skipping the deep audit."), file=sys.stderr)
        return False
    if deep_audit == "on":
        print(ui.dim(f"deep audit: {da.transport()}"))
        return True
    # auto: спрашиваем только в интерактивном терминале
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    try:
        ans = input(ui.bold(f"\nRun a deep LLM audit of {n} skill bodies before enabling them? "
                            f"(~{max(1, n // 8)}-{max(1, n // 4)} min, uses your "
                            f"{da.transport()}) [y/N] ")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans in ("y", "yes")


def _route(project, about, do_install, top=45, deep_audit="auto"):
    print(ui.banner())
    if not _ensure_data():
        return 1
    from . import select as select_mod, semantic
    prof = stack_mod.detect(project)
    facets, src = _load_facets(project, prof, about)

    stack_str = ", ".join(prof["platforms"]) or "—"
    fw_str = ", ".join(prof["frameworks"]) or "—"
    print(ui.bold("Detected stack:") + f"  {ui.green(stack_str)}   "
          + ui.dim("frameworks: ") + ui.green(fw_str))
    print(ui.bold(f"Facets ") + ui.dim(f"({src}, {len(facets)}):"))
    for f in facets:
        w = f.get("weight", 1.0)
        print(f"   {ui.cyan(f'{w:>3}')}  {f['facet']}")

    if not semantic.available():
        print("\n" + ui.yellow("Semantic index missing. Run:  skill-router update"), file=sys.stderr)
        return 1
    pstacks = select_mod.project_stacks(prof, _manifest_text(project))
    if pstacks:
        print(ui.dim(f"project stack (foreign excluded): {', '.join(sorted(pstacks))}"))
    try:
        picked = select_mod.select(facets, target=top, proj_stacks=pstacks)
    except RuntimeError as e:              # битые данные / модель не скачалась — без трейсбека
        print("\n" + ui.red(str(e)), file=sys.stderr)
        return 1
    byf = {}
    for p in picked:
        byf.setdefault(p["facet"], []).append(p)
    print("\n" + ui.bold(f"Skills to install ") + ui.cyan(f"({len(picked)})")
          + ui.dim(f" across {len(byf)} facets:"))
    i = 0
    for facet, rows in byf.items():
        print("  " + ui.dim("· ") + ui.bold(facet) + ui.dim(f" ({len(rows)})"))
        for p in rows:
            i += 1
            fl = (ui.yellow(" review") if p["needs_review"] else "") + (ui.yellow(" audit") if p["needs_audit"] else "")
            print(f"   {ui.dim(f'{i:>2}.')} {ui.blue(p['name'][:30]):<30}  "
                  + ui.gray(p['canon'][:30]) + f"  {ui.dim('rel')} {p['rel']}  {_risk_c(p['risk'])}{fl}")

    if not do_install:
        print("\n" + ui.dim("(dry-run — nothing installed. Run `skill-router .` to install.)"))
        return 0

    from . import install as install_mod
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not _check_rate(install_mod, token, len(picked)):
        return 1
    do_audit = _decide_deep_audit(deep_audit, len(picked))
    res = install_mod.install(project, picked, token=token, deep_audit=do_audit)
    print("\n" + ui.green(f"✔ installed {len(res['installed'])}")
          + ui.dim(f" → {os.path.join(project, '.claude', 'skills')}"))
    if res["blocked"]:
        print(ui.red(f"⛔ blocked (malware): ") + ", ".join(res["blocked"]))
    if res["screened"]:
        print(ui.red(f"⛔ blocked by local scan: ")
              + ", ".join(f"{n} ({fl})" for n, fl in res["screened"]))
    audited = res.get("audited") or []
    mal = [(n, r) for n, v, r in audited if v == "malicious"]
    susp = [(n, r) for n, v, r in audited if v == "suspicious"]
    if mal:
        print(ui.red(f"⛔ blocked by deep audit (malicious): ")
              + "; ".join(f"{n} — {r}" for n, r in mal))
    if susp:
        print(ui.yellow(f"● installed but flagged suspicious by deep audit: ")
              + "; ".join(f"{n} — {r}" for n, r in susp))
    if res["flagged"]:
        print(ui.yellow(f"● skipped (needs audit): ") + ", ".join(res["flagged"]))
    if res["changed"]:
        print(ui.yellow(f"● skipped (SHA mismatch, body changed): ") + ", ".join(res["changed"]))
    if res["no_sha"]:
        print(ui.yellow(f"● skipped (no SHA in catalog, unverifiable): ") + ", ".join(res["no_sha"]))
    if res["invalid"]:
        print(ui.yellow(f"● skipped (bad skill name): ") + ", ".join(res["invalid"][:8]))
    if res["failed"]:
        print(ui.dim(f"○ fetch failed: ") + ", ".join(res["failed"][:8]))
    if res.get("rate_limited") and not token:
        print(ui.yellow("GitHub API rate limit hit (60 req/h anonymous). "
                        "Set GITHUB_TOKEN to raise it to 5000 req/h."))
    return 0


def _safe_streams():
    """Windows: консоль cp1251 не кодирует ╔═╗/✔ → краш при редиректе. Заменяем, не падаем."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(errors="replace")
        except Exception:
            pass


COMMANDS = ("select", "install", "update", "ui")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    _safe_streams()

    # без подкоманды: `skill-router [path] [--top N]` — полный цикл.
    # Разбирается ДО argparse: сабпарсеры не пропускают неизвестный позиционный аргумент.
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help")):
        top, deep, rest = 45, "auto", []
        it = iter(argv)
        for a in it:
            if a == "--top":
                try:
                    top = max(1, int(next(it)))
                except (StopIteration, ValueError):
                    print("--top needs a number (e.g. --top 12)", file=sys.stderr)
                    return 2
            elif a == "--deep-audit":
                deep = "on"
            elif a == "--no-deep-audit":
                deep = "off"
            else:
                rest.append(a)
        if rest and rest[0].startswith("-"):
            print(f"unknown option: {rest[0]} (see skill-router --help)", file=sys.stderr)
            return 2
        project = rest[0] if rest else "."
        return _route(os.path.abspath(project), "", do_install=True, top=top, deep_audit=deep)

    p = argparse.ArgumentParser(prog="skill-router", description="Semantic router for Claude Code skills.")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("select", help="route only, do not install (dry-run)")
    sp.add_argument("project", nargs="?", default=".")
    sp.add_argument("--about", default="", help="project description (improves faceting)")
    sp.add_argument("--top", type=int, default=45,
                    help="how many skills to pick (default 45; 10-15 for a lean set)")

    ip = sub.add_parser("install", help="install specific skills by name")
    ip.add_argument("names", nargs="+")
    ip.add_argument("-p", "--project", default=".", help="target project dir (default: .)")

    up = sub.add_parser("update", help="pull latest catalog + index from GitHub Releases")
    up.add_argument("--force", action="store_true")

    uip = sub.add_parser("ui", help="open the catalog in a browser (list, tags, categories, filters)")
    uip.add_argument("--no-open", action="store_true", help="don't auto-open the browser")

    args = p.parse_args(argv)

    if args.cmd == "update":
        from . import update as update_mod
        return 0 if update_mod.update(force=args.force) else 1
    if args.cmd == "ui":
        if not _ensure_data():
            return 1
        from . import ui_server
        return ui_server.serve(open_browser=not args.no_open)
    if args.cmd == "select":
        return _route(os.path.abspath(args.project), args.about, do_install=False,
                      top=max(1, args.top))
    if args.cmd == "install":
        return _install_named(os.path.abspath(args.project), args.names)
    p.print_help()
    return 0


def _install_named(project, names):
    if not _ensure_data():
        return 1
    from . import select as select_mod, install as install_mod
    cat = select_mod._load_catalog()
    want = {n.lower() for n in names}
    # на каждое имя — лучший по рейтингу (одно имя бывает в разных репо)
    best = {}
    for c in cat.values():
        nm = (c.get("name") or "").lower()
        if nm in want and (nm not in best or (c.get("rating") or 0) > (best[nm].get("rating") or 0)):
            best[nm] = c
    rows = list(best.values())
    missing = want - set(best)
    if missing:
        print("не найдено в каталоге: " + ", ".join(sorted(missing)), file=sys.stderr)
    if not rows:
        return 1
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not _check_rate(install_mod, token, len(rows)):
        return 1
    res = install_mod.install(project, rows, token=token)
    print(f"installed: {len(res['installed'])}; blocked: {len(res['blocked'])}; "
          f"flagged: {len(res['flagged'])}; changed: {len(res['changed'])}; "
          f"no_sha: {len(res['no_sha'])}; local_scan: {len(res['screened'])}")
    if res["screened"]:
        print("blocked by local scan: "
              + ", ".join(f"{n} ({fl})" for n, fl in res["screened"]), file=sys.stderr)
    if res.get("rate_limited") and not token:
        print("GitHub API rate limit hit — set GITHUB_TOKEN to raise it.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
