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
import argparse

from . import config, stack as stack_mod, facets as facets_mod


def _need_data():
    if not config.data_ready():
        print("Каталог не найден. Запусти:  skill-router update", file=sys.stderr)
        return False
    return True


def _load_facets(project, prof, about):
    fp = os.path.join(project, ".claude", "skills-facets.json")
    if os.path.exists(fp):
        try:
            return json.loads(io.open(fp, encoding="utf-8").read()), "LLM"
        except Exception:
            pass
    return facets_mod.from_stack(prof, about), "stack fallback"


def _route(project, about, do_install):
    if not _need_data():
        return 1
    from . import select as select_mod, semantic
    prof = stack_mod.detect(project)
    facets, src = _load_facets(project, prof, about)

    print(f"stack: {', '.join(prof['platforms']) or '—'}  frameworks: {', '.join(prof['frameworks']) or '—'}")
    print(f"facets ({src}, {len(facets)}):")
    for f in facets:
        print(f"   {f.get('weight', 1.0):>3}  {f['facet']}")

    if not semantic.available():
        print("\nСемантический индекс не найден. Запусти:  skill-router update", file=sys.stderr)
        return 1
    picked = select_mod.select(facets, target=45)
    byf = {}
    for p in picked:
        byf.setdefault(p["facet"], []).append(p)
    print(f"\nselected: {len(picked)} skills across {len(byf)} facets")
    for facet, rows in byf.items():
        print(f"  · {facet} ({len(rows)}):")
        for p in rows:
            fl = ("[REVIEW]" if p["needs_review"] else "") + ("[AUDIT]" if p["needs_audit"] else "")
            print(f"      {p['rating']:>4}  {p['name'][:32]:<32} {p['canon']}  rel={p['rel']} risk:{p['risk'] or 'none'}{fl}")

    if not do_install:
        print("\n(dry-run — nothing installed. Use `skill-router .` to install.)")
        return 0

    from . import install as install_mod
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    res = install_mod.install(project, picked, token=token)
    print(f"\ninstalled: {len(res['installed'])} → {os.path.join(project, '.claude', 'skills')}")
    if res["blocked"]:
        print(f"blocked (malware): {', '.join(res['blocked'])}")
    if res["flagged"]:
        print(f"skipped (needs audit): {', '.join(res['flagged'])}")
    if res["changed"]:
        print(f"skipped (body changed since catalog, SHA mismatch): {', '.join(res['changed'])}")
    if res["failed"]:
        print(f"fetch failed (repo/path gone?): {', '.join(res['failed'][:8])}")
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="skill-router", description="Semantic router for Claude Code skills.")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("select", help="route only, do not install (dry-run)")
    sp.add_argument("project", nargs="?", default=".")
    sp.add_argument("--about", default="", help="project description (improves faceting)")

    ip = sub.add_parser("install", help="install specific skills by name")
    ip.add_argument("names", nargs="+")
    ip.add_argument("-p", "--project", default=".", help="target project dir (default: .)")

    up = sub.add_parser("update", help="pull latest catalog + index from GitHub Releases")
    up.add_argument("--force", action="store_true")

    args, extra = p.parse_known_args(argv)

    if args.cmd == "update":
        from . import update as update_mod
        return 0 if update_mod.update(force=args.force) else 1
    if args.cmd == "select":
        return _route(os.path.abspath(args.project), args.about, do_install=False)
    if args.cmd == "install":
        return _install_named(os.path.abspath(args.project), args.names)

    # без подкоманды: `skill-router .` (или без аргумента = текущая папка) — полный цикл
    project = argv[0] if argv and not argv[0].startswith("-") else "."
    return _route(os.path.abspath(project), "", do_install=True)


def _install_named(project, names):
    if not _need_data():
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
    res = install_mod.install(project, rows, token=token)
    print(f"installed: {len(res['installed'])}; blocked: {len(res['blocked'])}; "
          f"flagged: {len(res['flagged'])}; changed: {len(res['changed'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
