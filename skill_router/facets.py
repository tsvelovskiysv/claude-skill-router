"""Фолбэк-грани без LLM: из стека + описания. Хуже LLM-граней, но работает офлайн.

Боевой путь — грани от LLM (файл .claude/skills-facets.json), см. README.
"""
import re

STOP = set("the a an and or for with your you our are was this that app project service "
           "using build make create tool app".split())


def from_stack(prof, about=""):
    facets = []
    for fw in (prof.get("frameworks") or []):
        facets.append({"facet": fw, "weight": 1.0})
    st = " ".join(prof.get("stack_terms") or [])
    if st:
        facets.append({"facet": st, "weight": 1.0})
    words = [w for w in re.findall(r"[a-z][a-z\-]{2,}", (about or "").lower()) if w not in STOP]
    seen, dom = set(), []
    for w in words:
        if w not in seen:
            seen.add(w); dom.append(w)
    for i in range(0, min(len(dom), 12), 4):
        facets.append({"facet": " ".join(dom[i:i + 4]), "weight": 0.8})
    if (about or "").strip():
        facets.append({"facet": about.strip()[:120], "weight": 0.7})
    if prof.get("is_ui"):
        facets.append({"facet": "ui ux design visual", "weight": 0.7})
        facets.append({"facet": "animations motion transitions", "weight": 0.5})
    facets.append({"facet": "testing quality", "weight": 0.5})
    out, seent = [], set()
    for f in facets:
        k = f["facet"].lower().strip()
        if k and k not in seent:
            seent.add(k); out.append(f)
    return out[:15]
