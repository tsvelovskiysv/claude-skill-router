"""Детект стека проекта по файлам-маркерам. Кроссплатформенно, без хардкода.

Один проход os.walk с отсечением служебных папок (node_modules/.git/…): иначе на
JS-проекте обход длится минуты, а package.json из node_modules искажает стек.
"""
import os
import io
import json

# маркер-файл → (метка, поисковые термины)
MARKERS = [
    ("build.gradle.kts", "android", ["android", "kotlin", "jetpack compose", "gradle"]),
    ("build.gradle", "android", ["android", "kotlin", "gradle"]),
    ("AndroidManifest.xml", "android", ["android"]),
    ("Package.swift", "ios", ["ios", "swift", "swiftui"]),
    ("Podfile", "ios", ["ios", "swift"]),
    ("pubspec.yaml", "flutter", ["flutter", "dart", "mobile"]),
    ("next.config.js", "nextjs", ["next.js", "react", "frontend"]),
    ("next.config.ts", "nextjs", ["next.js", "react", "frontend"]),
    ("requirements.txt", "python", ["python"]),
    ("pyproject.toml", "python", ["python"]),
    ("Cargo.toml", "rust", ["rust"]),
    ("go.mod", "go", ["go", "golang"]),
    ("pom.xml", "java", ["java", "maven"]),
    ("composer.json", "php", ["php"]),
    ("Gemfile", "ruby", ["ruby", "rails"]),
]
_MARKER_BY_NAME = {m[0].lower(): (m[1], m[2]) for m in MARKERS}
EXT_HINT = {".kt": ("android", ["kotlin"]), ".swift": ("ios", ["swift"]),
            ".dart": ("flutter", ["dart"]), ".py": ("python", ["python"]),
            ".rs": ("rust", ["rust"]), ".go": ("go", ["go"])}
UI_STACKS = {"android", "ios", "flutter", "nextjs", "react", "react-native", "vue", "frontend"}
DB_MARKERS = {"docker-compose": "docker", "schema.prisma": "prisma", "supabase": "supabase"}

# служебное/чужое — не проект: и медленно, и врёт про стек
SKIP_DIRS = {"node_modules", ".git", ".hg", ".svn", ".venv", "venv", "env", "vendor",
             "dist", "build", "out", "target", "__pycache__", ".next", ".nuxt",
             ".cache", ".idea", ".vscode", "coverage", "Pods", "DerivedData"}


def iter_files(project_dir, max_files=50000):
    """Пути файлов проекта одним проходом, служебные папки отсечены."""
    n = 0
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in files:
            yield os.path.join(root, f)
            n += 1
            if n >= max_files:
                return


def _js_stack(pj_path, found, frameworks):
    try:
        # utf-8-sig: package.json с BOM (частое на Windows) иначе молча отбрасывается
        data = json.loads(io.open(pj_path, encoding="utf-8-sig").read())
    except Exception:
        return
    deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
    keys = {k.lower() for k in deps}
    # точное имя пакета, не подстрока: иначе preact считается react
    if "react-native" in keys or "expo" in keys:
        found.setdefault("react-native", set()).update(["react native", "mobile", "expo"])
    elif "next" in keys:
        found.setdefault("nextjs", set()).update(["next.js", "react", "frontend"])
    elif "react" in keys:
        found.setdefault("react", set()).update(["react", "frontend"])
    elif "vue" in keys or "nuxt" in keys:
        found.setdefault("vue", set()).update(["vue", "frontend"])
    else:
        found.setdefault("node", set()).update(["node", "javascript"])
    dl = " ".join(keys)
    for fw in ("tailwind", "prisma", "supabase", "express", "fastify", "vite"):
        if fw in dl:
            frameworks.add(fw)


def detect(project_dir):
    found = {}
    frameworks, dbs = set(), set()
    exts = set()

    for path in iter_files(project_dir):
        base = os.path.basename(path)
        low = base.lower()
        hit = _MARKER_BY_NAME.get(low)
        if hit:
            found.setdefault(hit[0], set()).update(hit[1])
        if low == "package.json":
            _js_stack(path, found, frameworks)
        for m, name in DB_MARKERS.items():
            if m in low:
                dbs.add(name)
        if len(exts) < 200:
            exts.add(os.path.splitext(base)[1])

    if not found:
        for ext, (tag, terms) in EXT_HINT.items():
            if ext in exts:
                found.setdefault(tag, set()).update(terms)

    platforms = sorted(found)
    terms = sorted({t for ts in found.values() for t in ts})
    return {
        "platforms": platforms,
        "stack_terms": terms,
        "frameworks": sorted(frameworks),
        "databases": sorted(dbs),
        "is_ui": any(p in UI_STACKS for p in platforms),
        "is_code": bool(platforms or frameworks or terms),
    }
