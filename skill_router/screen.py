"""Client-side слой-1: перепроверка скачанного тела ПЕРЕД записью на диск.

Порт правил статического скрининга из пайплайна каталога. Независим от каталога:
даже если каталог скомпрометирован или скилл не проходил LLM-аудит (не был
флагнут), клиент сам ловит известные malware-паттерны локально, без сети и LLM.

  hard   — доказанный malware-паттерн (obfuscated exec, архив под паролем,
           IP-дроппер) → не ставим никогда;
  review — подозрительный (curl|bash, эксфильтрация, destructive,
           prompt injection) → не ставим, сообщаем.

Пример внутри явного запрета («Do NOT install via curl|bash») — не находка
(review-класс); hard-паттерны без этой поблажки: вредонос не спрячется за «never».
"""
import re
import ipaddress

# ---- hard: доказанный malware ----
RE_B64_EXEC_PIPE = re.compile(
    r"\bbase64\s+(?:-d\b|--decode\b)[^\n|]{0,150}\|\s*(?:sudo\s+)?(?:bash|sh|zsh)\b"
    r"|\bxxd\b[^\n|]{0,30}-r\b[^\n|]{0,60}\|\s*(?:sudo\s+)?(?:bash|sh|zsh)\b"
    r"|\b(?:powershell(?:\.exe)?|pwsh)\b[^\n]{0,60}-enc(?:odedcommand)?\b\s+[A-Za-z0-9+/=]{16,}"
    r"|\bfrombase64string\b[^\n]{0,300}\b(?:iex|invoke-expression)\b"
    r"|\b(?:iex|invoke-expression)\b[^\n]{0,300}\bfrombase64string\b",
    re.I)
RE_FROMBASE64 = re.compile(r"\bfrombase64string\b", re.I)
RE_IEX_WORD = re.compile(r"\b(?:iex|invoke-expression)\b", re.I)
RE_PASSWORD_ARCHIVE = re.compile(
    r"\b7z[ar]?\s+[ex]\b[^\n]{0,30}-p\S+"
    r"|\b(?:extract|unzip|decompress|open)\b[^\n]{0,20}\b(?:with|using)\b[^\n]{0,15}"
    r"\b(?:password\b|pass\b\s*:?\s*`[^\n`]{1,40}`)"
    r"|\bpassword[- ]protected\b[^\n]{0,20}\b(?:zip|archive|rar|7z|file)\b"
    r"|\b(?:zip|archive|rar|7z)\b[^\n]{0,20}\bpassword[- ]protected\b"
    r"|\bExpand-Archive\b[^\n]{0,150}\bpassword\b"
    r"|\bpassword\b[^\n]{0,150}\bExpand-Archive\b",
    re.I)
RE_UNZIP_PASSWORD = re.compile(r"\bunzip\b[^\n]{0,30}-P\s*\S+")
RE_IP_PIPE_SHELL = re.compile(
    r"\b(?:curl|wget)\b[^\n|]{0,150}https?://([\w.-]+)(?::\d+)?[^\n|]{0,80}\|\s*(?:sudo\s+)?(?:bash|sh|zsh)\b",
    re.I)
RE_IP_CMD_SUBST = re.compile(
    r"\$\(\s*(?:curl|wget)\b[^\n)]{0,200}https?://([\w.-]+)(?::\d+)?[^\n)]{0,80}\)",
    re.I)

# ---- review: подозрительное ----
RE_PIPE_SHELL = re.compile(
    r"\b(?:curl|wget)\b[^\n|]{0,200}\|\s*(?:sudo\s+)?(?:bash|sh|zsh)\b"
    r"|\b(?:iex|invoke-expression)\s*\(?\s*(?:irm\b|invoke-restmethod\b|new-object\s+net\.webclient)"
    r"|\b(?:irm|invoke-restmethod)\b[^\n|]{0,200}\|\s*(?:iex|invoke-expression)\b"
    r"|\bbase64\s+(?:-d|--decode)\b[^\n|]{0,80}\|\s*(?:bash|sh|zsh)\b",
    re.I)
RE_EXFIL = re.compile(
    r"\b(?:curl|wget)\b[^\n]{0,150}(?:-X\s*POST|--data\S*|-d\s|-F\s)[^\n]{0,150}"
    r"\$\{?(?:[A-Z][A-Z0-9_]*_)?(?:TOKEN|SECRET|API_?KEY|PASSWORD|PASSWD|CREDENTIALS?|AWS_[A-Z_]+)\w*\}?"
    r"|\b(?:cat|type)\s+[^\n|]{0,60}(?:\.env\b|credentials\b|secrets?\.\w+)[^\n]{0,80}\|\s*(?:curl|wget|nc\b|ncat\b)"
    r"|\b(?:env|printenv)\b[^\n]{0,40}\|\s*(?:curl|wget|nc\b|ncat\b)"
    r"|https?://[^\s<>()]{0,150}\$\{?(?:[A-Z][A-Z0-9_]*_)?(?:TOKEN|SECRET|API_?KEY|PASSWORD)\w*\}?",
    re.I)
RE_RM_LINE = re.compile(r"\brm\s+[^\n]{0,80}", re.I)
RE_RM_RF = re.compile(
    r"^rm\s+-(?=[a-zA-Z]{1,4}\b)(?=[a-zA-Z]*r)(?=[a-zA-Z]*f)[a-zA-Z]+\b"
    r"|^rm\s+(?:-[a-zA-Z]+\s+)*--recursive\b(?:\s+-[a-zA-Z]+)*\s+--force\b"
    r"|^rm\s+(?:-[a-zA-Z]+\s+)*--force\b(?:\s+-[a-zA-Z]+)*\s+--recursive\b"
    r"|^rm\s+-r\s+-f\b|^rm\s+-f\s+-r\b",
    re.I)
RE_DANGEROUS_TARGET = re.compile(r"(?:\s|^)(?:/(?:\s|$)|/\*|~(?:\s|$|/)|\$HOME\b|\*\s*$|--no-preserve-root)")
RE_OTHER_DESTRUCTIVE = re.compile(
    r"\bmkfs(?:\.\w+)?\b"
    r"|\bdd\s+[^\n]{0,60}\bof=/dev/(?:sd|hd|nvme|disk|xvd)\w*"
    r"|\bformat\s+[a-zA-Z]:\s"
    r"|\bdiskpart\b"
    r"|\bRemove-Item\b[^\n]{0,80}-Recurse\b[^\n]{0,40}-Force\b[^\n]{0,40}[a-zA-Z]:\\?(?:\s|$)"
    r"|\bfind\s+[^\n]{0,40}-delete\b"
    r"|\bgit\s+clean\s+-(?=[a-zA-Z]{1,5}\b)(?=[a-zA-Z]*x)(?=[a-zA-Z]*d)(?=[a-zA-Z]*f)[a-zA-Z]+\b"
    r"|\b(?:del|erase)\s+/[fFsSqQ]+\s+/[fFsSqQ]+\b",
    re.I)
RE_PROMPT_INJECTION = re.compile(
    r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|prompts?|rules|guidelines)\b"
    r"|\bdisregard\s+(?:all\s+|your\s+|the\s+)?(?:previous|prior|system|safety|above)?\s*(?:instructions?|guidelines|rules)\b"
    r"|\byou\s+are\s+(?:now\s+)?(?:DAN\b|in\s+developer\s+mode\b)"
    r"|\bdo\s+anything\s+now\b"
    r"|\bjailbreak(?:s|ing|ed)?\b"
    r"|\bwithout\s+(?:revealing|telling|informing|showing|asking)\s+(?:the\s+)?user\b"
    r"|\b(?:do\s+not|don't|never)\s+(?:tell|inform|mention|reveal|show)\s+(?:this|that)?\s*(?:to\s+)?(?:the\s+)?user\b"
    r"|\bhide\s+(?:this|these|your|the)\s+(?:actions?|reasoning|steps?|process)\s+from\s+(?:the\s+)?user\b"
    r"|\bact\s+as\s+(?:if\s+you\s+have\s+no\s+restrictions|an\s+unfiltered\s+ai)\b"
    r"|\bpretend\s+(?:you\s+have\s+no|there\s+are\s+no)\s+(?:guidelines|restrictions|rules)\b",
    re.I)

RE_NEGATION = re.compile(
    r"\b(?:do\s+not|don[’']?t|never|avoid|must\s+not|instead\s+of|"
    r"not\s+recommended|rather\s+than)\b", re.I)

# --- обходы, найденные внешним аудитом (targeted, не commodity) ---

# 1. дроппер прозой: «download helper.sh … and run it» — без curl|bash в строку.
# Требуем И скачивание скрипта, И ПЕРЕХОДНЫЙ глагол исполнения, указывающий на скачанное
# (run it / execute the script / ./that), а не голое слово «run» (иначе ловит «between runs»,
# «clean run», «source code»).
_RUN_OBJ = (r"(?:run|execute|exec|launch|invoke)\s+"
            r"(?:it|this|that|them|the\s+(?:script|file|installer|binary|payload|above|downloaded\s+\w+))\b"
            r"|(?:bash|sh|zsh|\./)\s*[\w./-]+\.(?:sh|ps1|py|bat|cmd|rb|pl)\b")
RE_PROSE_DROP = re.compile(
    r"(?:download|fetch|grab|retrieve|curl|wget)\b[^\n]{0,120}"
    r"\b[\w./-]+\.(?:sh|ps1|py|bat|cmd|rb|pl)\b[^\n]{0,200}"
    r"(?:" + _RUN_OBJ + r")"
    r"|\b[\w./-]+\.(?:sh|ps1|py|bat|cmd|rb|pl)\b[^\n]{0,120}"
    r"\b(?:download|fetch|grab|retrieve)\b[^\n]{0,80}(?:" + _RUN_OBJ + r")",
    re.I)

# 2. двухступенчатый base64: декод В ФАЙЛ, затем запуск этого файла отдельной строкой.
#    base64 -d ... > out.sh   +   позже   bash out.sh
RE_B64_TO_FILE = re.compile(
    r"\b(?:base64\s+(?:-d|--decode)|xxd\s+-r)\b[^\n]{0,80}>\s*([\w./-]+)", re.I)

# 3. интерпретатор -c/-e со скачиванием и исполнением в одном вызове:
#    python -c "...urlopen(...).read()...exec(...)", node -e "...fetch(...)...eval(..."
RE_INTERP_FETCH_EXEC = re.compile(
    r"\b(?:python[23]?|node|ruby|perl)\b[^\n]{0,10}(?:-c|-e)\b[^\n]{0,400}"
    r"(?:urlopen|urlretrieve|requests\.get|urllib|fetch\s*\(|net/http|open-uri|https?://)"
    r"[^\n]{0,400}(?:\bexec\s*\(|\beval\s*\(|\bexecfile\b|Function\s*\(|\bsystem\s*\(|`)",
    re.I)


def _b64_to_file_then_run(text):
    """decode→файл на одной строке, запуск того же файла — на другой."""
    for m in RE_B64_TO_FILE.finditer(text):
        fname = re.escape(m.group(1).strip())
        # тот же файл позже исполняется: bash out.sh / sh out.sh / ./out.sh / python out.py
        run = re.compile(r"(?:bash|sh|zsh|python[23]?|node|ruby|perl|\./)\s*[\"']?"
                         + fname + r"\b", re.I)
        if run.search(text):
            return True
    return False


def _ip_is_public(host):
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _negated(text, start):
    ctx = text[max(0, start - 300):start]
    para = re.split(r"\n\s*\n", ctx)[-1]
    return bool(RE_NEGATION.search(para))


def _destructive(text):
    for m in RE_RM_LINE.finditer(text):
        if RE_RM_RF.match(m.group(0)) and RE_DANGEROUS_TARGET.search(m.group(0)):
            return True
    return bool(RE_OTHER_DESTRUCTIVE.search(text))


def _obfuscated(text):
    if RE_B64_EXEC_PIPE.search(text):
        return True
    if RE_FROMBASE64.search(text) and RE_IEX_WORD.search(text):
        return True
    return _b64_to_file_then_run(text)          # двухступенчатый base64 (обход из аудита)


def _ip_dropper(text):
    for rx in (RE_IP_PIPE_SHELL, RE_IP_CMD_SUBST):
        for m in rx.finditer(text):
            if _ip_is_public(m.group(1)):
                return True
    return False


def _pipe_shell(text):
    return any(not _negated(text, m.start()) for m in RE_PIPE_SHELL.finditer(text))


def _fetch_exec(text):
    """скачивание+исполнение, разнесённое по прозе/строкам (обходы из аудита)."""
    for m in RE_PROSE_DROP.finditer(text):
        if not _negated(text, m.start()):
            return True
    return bool(RE_INTERP_FETCH_EXEC.search(text))


def verdict(body):
    """bytes/str тела → ('hard'|'review', flag_id) или (None, None) если чисто."""
    text = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else body
    if _obfuscated(text):
        return "hard", "obfuscated_exec"
    if RE_PASSWORD_ARCHIVE.search(text) or RE_UNZIP_PASSWORD.search(text):
        return "hard", "password_archive"
    if _ip_dropper(text):
        return "hard", "ip_dropper"
    if _pipe_shell(text):
        return "review", "pipe_to_shell"
    if _fetch_exec(text):
        return "review", "fetch_exec"
    if RE_EXFIL.search(text):
        return "review", "exfiltration"
    if _destructive(text):
        return "review", "destructive"
    if RE_PROMPT_INJECTION.search(text):
        return "review", "prompt_injection"
    return None, None
