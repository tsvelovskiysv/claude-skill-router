"""Детект стека проекта по файлам-маркерам. Кроссплатформенно, без хардкода."""
import os
import io
import json
import glob

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
EXT_HINT = {".kt": ("android", ["kotlin"]), ".swift": ("ios", ["swift"]),
            ".dart": ("flutter", ["dart"]), ".py": ("python", ["python"]),
            ".rs": ("rust", ["rust"]), ".go": ("go", ["go"])}
UI_STACKS = {"android", "ios", "flutter", "nextjs", "react", "react-native", "vue", "frontend"}
DB_MARKERS = {"docker-compose.yml": "docker", "schema.prisma": "prisma", "supabase": "supabase"}


def detect(project_dir):
    found = {}
    frameworks, dbs = set(), set()

    for marker, tag, terms in MARKERS:
        if glob.glob(os.path.join(project_dir, "**", marker), recursive=True):
            found.setdefault(tag, set()).update(terms)

    for pj in glob.glob(os.path.join(project_dir, "**", "package.json"), recursive=True):
        try:
            data = json.loads(io.open(pj, encoding="utf-8").read())
        except Exception:
            continue
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        dl = " ".join(deps).lower()
        if "react-native" in dl or "expo" in dl:
            found.setdefault("react-native", set()).update(["react native", "mobile", "expo"])
        elif "next" in dl:
            found.setdefault("nextjs", set()).update(["next.js", "react", "frontend"])
        elif "react" in dl:
            found.setdefault("react", set()).update(["react", "frontend"])
        elif "vue" in dl:
            found.setdefault("vue", set()).update(["vue", "frontend"])
        else:
            found.setdefault("node", set()).update(["node", "javascript"])
        for fw in ("tailwind", "prisma", "supabase", "express", "fastify", "vite"):
            if fw in dl:
                frameworks.add(fw)

    for m, name in DB_MARKERS.items():
        if glob.glob(os.path.join(project_dir, "**", "*" + m + "*"), recursive=True):
            dbs.add(name)

    if not found:
        exts = {os.path.splitext(f)[1]
                for f in glob.glob(os.path.join(project_dir, "**", "*"), recursive=True)[:2000]}
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
