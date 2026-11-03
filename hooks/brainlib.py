"""
Shared utilities for the BERNARD Brain Kit hooks and CLI: paths, config, the vault map and index,
the two rankers, session state and the rule loader. Standard library only; Python 3.8+.
"""
import os
import sys
import re
import json
import math
import time
import hashlib
import datetime
import importlib.util
try:
    import fcntl  # the session lock; missing on Windows, where the lock becomes a no-op
except Exception:  # pragma: no cover
    fcntl = None

# Constants
PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOME = os.path.expanduser("~")
BERNARD_DIR = os.getenv("BERNARD_HOME", os.path.join(HOME, ".bernard"))
CONFIG = os.path.join(BERNARD_DIR, "config.json")
STATE_DIR = os.path.join(BERNARD_DIR, "state")
LOG = os.path.join(BERNARD_DIR, "log.txt")
DEFAULT_VAULT = os.path.join(HOME, "brain")
NOTE_DIRS = ["topics", "patterns", "references", "projects", "skills", "sessions"]
EXCLUDED_DIRS = {
    "devlog", "templates", "rules", "attachments", "_archive",
    ".obsidian", ".git", ".trash", "node_modules"
}
MAP_NAME = "MAP.md"
INDEX_NAME = ".index.json"
MAX_PACKET = 8600
MAX_NOTES = 5
MAX_SKILLS = 2
MAX_PROJECTS = 2
MIN_SCORE = 4
PER_NOTE_FLOOR = 550
BM25_POOL = 20
STOP = {
    "a","an","and","are","as","at","be","but","by","can","could","did","do","does",
    "for","from","get","got","had","has","have","how","i","if","in","into","is",
    "it","its","just","like","make","made","me","might","must","my","need","not",
    "of","on","one","or","our","out","over","please","should","so","some","such",
    "than","that","the","their","them","then","there","these","they","this","those",
    "to","too","use","used","using","want","was","we","were","what","when","where",
    "which","who","why","will","with","would","you","your","about","after","also",
    "any","because","been","before","being","between","both","each","few","more",
    "most","other","same","through","under","only","very","own","don","doesn",
    "isn","wasn","let","lets","ll","ve","re","thing","things","way","ways","new",
    "now","okay","ok","yes","no","thanks","thank","back","again","still","even",
    "ever","never","always"
}
PROJ_NOISE = {"project","new","old","misc","src","app","main","test","tmp"}

FENCE = "`" * 3

def _ensure_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass

def log(msg: str):
    """Append a timestamped message to the log file."""
    try:
        _ensure_dir(os.path.dirname(LOG))
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except Exception:
        pass

def read_stdin_json():
    """Read JSON from stdin, return {} on any error."""
    try:
        data = sys.stdin.read()
        return json.loads(data) if data.strip() else {}
    except Exception:
        return {}

def emit(event_name, text):
    """Print a JSON packet with additionalContext."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": text
        }
    }
    print(json.dumps(payload, ensure_ascii=False))

def load_config():
    """Load config.json, return {} if missing or bad."""
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(cfg):
    """Save config atomically with indent=1."""
    try:
        _ensure_dir(os.path.dirname(CONFIG))
        tmp = CONFIG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1, ensure_ascii=False)
        os.replace(tmp, CONFIG)
    except Exception as e:
        log(f"save_config error: {e}")

def vault_path():
    """Resolve the vault directory."""
    env = os.getenv("BERNARD_VAULT")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    cfg = load_config()
    v = cfg.get("vault")
    if v:
        return os.path.abspath(os.path.expanduser(v))
    return os.path.abspath(os.path.expanduser(DEFAULT_VAULT))

def vault_exists(vault=None):
    """Check if vault folder exists and contains index.md or MAP.md."""
    v = vault or vault_path()
    if not os.path.isdir(v):
        return False
    return any(os.path.isfile(os.path.join(v, name)) for name in ("index.md", MAP_NAME))

def slugify(name):
    s = name.lower()
    s = re.sub(r"[ _]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "unknown-project"

def project_hint(cwd):
    base = os.path.basename(cwd.rstrip("/"))
    slug = slugify(base)
    cfg = load_config()
    return cfg.get("dir_to_project", {}).get(slug, slug)

def strip_frontmatter(text):
    if text.startswith("---"):
        parts = text.split("\n")
        for i in range(1, len(parts)):
            if parts[i].strip() == "---":
                return "\n".join(parts[i+1:])
    return text

def first_sentence(body):
    txt = strip_frontmatter(body)
    lines = txt.splitlines()
    in_fence = False
    for line in lines:
        if line.strip().startswith(FENCE):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if re.match(r"[-*+]\s", stripped):
            continue
        if re.match(r"\d+\.\s", stripped):
            continue
        if stripped.startswith("|"):
            continue
        if stripped.startswith(">"):
            continue
        if stripped.startswith("<"):
            continue
        # clean links and markup
        line = re.sub(r"\[\[.+?/([^/\]]+)\]\]", r"\1", stripped)
        line = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", line)
        line = re.sub(r"[*_`]", "", line)
        if len(line) > 30 and ". " in line[30:]:
            line = line[:line.find(". ", 30)+1]
        if len(line) > 140:
            line = line[:140] + "…"
        return line
    return ""

def list_notes(vault):
    notes = []
    for root, dirs, files in os.walk(vault):
        # prune excluded dirs
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith('.')]
        rel_root = os.path.relpath(root, vault)
        if rel_root == ".":
            continue  # files at the vault root (index.md, MAP.md) are not notes
        for f in files:
            if not f.lower().endswith(".md"):
                continue
            if f in (MAP_NAME, "index.md"):
                continue
            if f.startswith("in-progress-"):
                continue
            abs_path = os.path.join(root, f)
            rel_path = os.path.relpath(abs_path, vault)
            if rel_path.startswith("./"):
                rel_path = rel_path[2:]
            rel_no_md = rel_path[:-3]  # strip .md
            notes.append((rel_no_md.replace(os.sep, "/"), abs_path))
    notes.sort(key=lambda x: x[0])
    return notes

def tokens(text):
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in toks if len(t) >= 3 and t not in STOP]

def stem(t):
    if len(t) > 4:
        if t.endswith("ies"):
            t = t[:-3] + "y"
        elif t.endswith(("sses","shes","ches")):
            t = t[:-2]
        elif t.endswith("ing") and len(t) > 5:
            t = t[:-3]
        elif t.endswith("ed"):
            t = t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        t = t[:-1]
    return t

def expand(toks, syn):
    exact = set(toks)
    for t in toks:
        for s in syn.get(t, []):
            exact.update(tokens(s))
    stems = {stem(t) for t in toks}
    prefixes = {t[:6] for t in toks if len(t) >= 5}
    return exact, stems, prefixes

def inventory_hash(notes):
    """A short fingerprint of WHICH notes exist (their paths), so a rename or delete is seen even when no mtime moved."""
    joined = "\n".join(rel for rel, _ in notes)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]

def build_map(vault):
    entries = []
    df = {}
    docs = {}
    total_len = 0
    notes = list_notes(vault)
    for rel, abs_path in notes:
        kind = rel.split("/")[0]
        with open(abs_path, "r", encoding="utf-8") as f:
            body = f.read()
        desc = first_sentence(body) or "(no description yet: add one plain sentence under the title)"
        entries.append((rel, kind, desc))
        # index building: tf counts every occurrence of a stem, df counts each note once
        txt = strip_frontmatter(body)[:4000]
        toks = tokens(txt)
        doc_len = len(toks)
        total_len += doc_len
        tf = {}
        for t in toks:
            s = stem(t)
            tf[s] = tf.get(s, 0) + 1
        for s in tf:
            df[s] = df.get(s, 0) + 1
        docs[rel] = {"len": doc_len, "tf": tf}
    N = len(entries)
    avgdl = total_len / N if N else 0.0
    index = {"n": N, "avgdl": avgdl, "df": df, "docs": docs}
    # write MAP.md
    map_lines = [
        "# Brain map",
        "",
        f"*Generated by `brain map`. Do not edit by hand.*",
        f"*Last built: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"*Inventory: {inventory_hash(notes)}*",
        "",
        "Every note in the vault with a one-line description. Read this to find prior work instead of listing folders.",
        "",
        "## Contents",
        ""
    ]
    kind_counts = {}
    for _, kind, _ in entries:
        kind_counts[kind] = kind_counts.get(kind,0)+1
    for kd in NOTE_DIRS:
        if kd in kind_counts:
            map_lines.append(f"- **{kd}** — {kind_counts[kd]}")
    other_kinds = sorted([k for k in kind_counts if k not in NOTE_DIRS])
    for kd in other_kinds:
        map_lines.append(f"- **{kd}** — {kind_counts[kd]}")
    map_lines.append("")
    for kd in NOTE_DIRS + other_kinds:
        if kd not in kind_counts:
            continue
        map_lines.append(f"## {kd}/")
        map_lines.append("")
        groups = {}
        for rel, kind, desc in entries:
            if kind != kd:
                continue
            parts = rel.split("/")
            domain = "/".join(parts[1:-1]) if len(parts) > 2 else ""
            slug = parts[-1]
            groups.setdefault(domain, []).append((slug, desc))
        for domain, items in sorted(groups.items()):
            header = f"### {kd}/{domain}" if domain else f"### {kd}"
            map_lines.append(f"{header}  ({len(items)})")
            map_lines.append("")
            for slug, desc in items:
                link = f"[[{kd}/{domain}/{slug}]]" if domain else f"[[{kd}/{slug}]]"
                map_lines.append(f"- {link} — {desc}")
            map_lines.append("")
    map_content = "\n".join(map_lines).strip() + "\n"
    map_path = os.path.join(vault, MAP_NAME)
    idx_path = os.path.join(vault, INDEX_NAME)
    # two sessions may rebuild the same vault at the same moment: each writes its own temp file (pid in the name)
    # and publishes it with an atomic rename, so a reader only ever sees a complete MAP.md and .index.json
    tmp_map = f"{map_path}.{os.getpid()}.tmp"
    tmp_idx = f"{idx_path}.{os.getpid()}.tmp"
    try:
        with open(tmp_map, "w", encoding="utf-8") as f:
            f.write(map_content)
        with open(tmp_idx, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
        os.replace(tmp_idx, idx_path)
        os.replace(tmp_map, map_path)
    except Exception as e:
        log(f"build_map write error: {e}")
        for t in (tmp_map, tmp_idx):
            try:
                os.remove(t)
            except Exception:
                pass
    return N

class map_lock(object):
    """One map rebuild per vault at a time (`with map_lock(vault) as lk: if lk.acquired: ...`). The lock file lives
    in the plugin's state folder, never in the vault. Waits up to `timeout` seconds; `acquired` says whether it
    got the lock; a no-op (acquired) where fcntl is missing."""

    def __init__(self, vault, timeout=3.0):
        tag = hashlib.sha1(os.path.realpath(vault).encode("utf-8")).hexdigest()[:12]
        self.path = os.path.join(STATE_DIR, f"map-{tag}.lock")
        self.timeout = timeout
        self.fh = None
        self.acquired = False

    def __enter__(self):
        if fcntl is None:
            self.acquired = True
            return self
        try:
            _ensure_dir(STATE_DIR)
            self.fh = open(self.path, "a+")
            deadline = time.time() + self.timeout
            while True:
                try:
                    fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.acquired = True
                    return self
                except OSError:
                    if time.time() >= deadline:
                        return self
                    time.sleep(0.02)
        except Exception as e:
            log(f"map_lock error: {e}")
            return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fh is not None:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
                self.fh.close()
        except Exception:
            pass
        return False

def index_is_readable(vault):
    """True when .index.json parses and has the shape the router reads."""
    try:
        with open(os.path.join(vault, INDEX_NAME), "r", encoding="utf-8") as f:
            idx = json.load(f)
        return isinstance(idx, dict) and isinstance(idx.get("docs"), dict) and "n" in idx and "df" in idx
    except Exception:
        return False

def map_inventory(vault):
    """The inventory fingerprint recorded in MAP.md's header, or None when the map has none."""
    try:
        with open(os.path.join(vault, MAP_NAME), "r", encoding="utf-8") as f:
            for _ in range(12):
                line = f.readline()
                if not line:
                    break
                m = re.search(r"Inventory:\s*([0-9a-f]{6,})", line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None

def map_is_stale(vault):
    """True when a note changed since the map was built, or a note was added, renamed or deleted."""
    map_path = os.path.join(vault, MAP_NAME)
    idx_path = os.path.join(vault, INDEX_NAME)
    if not (os.path.isfile(map_path) and os.path.isfile(idx_path)):
        return True
    if not index_is_readable(vault):
        return True  # a half-written or damaged index is rebuilt, never served
    map_mtime = os.path.getmtime(map_path)
    notes = list_notes(vault)
    if map_inventory(vault) != inventory_hash(notes):
        return True
    for _, abs_path in notes:
        if os.path.getmtime(abs_path) > map_mtime:
            return True
    return False

def ensure_map(vault):
    """Rebuild the map when it is stale. One session rebuilds at a time: a hook that finds another session
    building waits up to 3 s, then re-checks, so it never writes on top of the other build."""
    try:
        if not map_is_stale(vault):
            return False
        with map_lock(vault) as lk:
            if not lk.acquired:
                return False  # the other build publishes a complete map; this prompt uses what is there
            if map_is_stale(vault):  # the other session may have just rebuilt it
                build_map(vault)
                return True
        return False
    except Exception as e:
        log(f"ensure_map error: {e}")
        return False

def parse_map(vault):
    entries = []
    map_path = os.path.join(vault, MAP_NAME)
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^- \[\[([^\]]+)\]\]\s*[—-]?\s*(.*)$", line)
                if m:
                    path = m.group(1)
                    if path.startswith("in-progress-"):
                        continue
                    parts = path.split("/")
                    kind = parts[0] if parts else ""
                    domain = "/".join(parts[1:-1]) if len(parts) > 2 else ""
                    slug = parts[-1] if parts else ""
                    desc = m.group(2).strip()
                    entries.append({
                        "path": path,
                        "kind": kind,
                        "domain": domain,
                        "slug": slug,
                        "desc": desc
                    })
    except Exception as e:
        log(f"parse_map error: {e}")
    return entries

def score_entry(entry, bands, proj_bands, prompt_l, proj):
    slug = entry["slug"]
    desc = entry["desc"]
    slug_toks = set(tokens(slug.replace("-", " ")))
    desc_toks = set(tokens(desc))
    exact, stems, prefixes = bands
    slug_stems = {stem(t) for t in slug_toks}
    desc_stems = {stem(t) for t in desc_toks}
    slug_pre = {t[:6] for t in slug_toks if len(t) >=5}
    desc_pre = {t[:6] for t in desc_toks if len(t) >=5}
    s = 0
    s += 4 * len(exact & slug_toks)
    s += 1 * len(exact & desc_toks)
    s += 2 * len((stems & slug_stems) - (exact & slug_toks))
    s += 1 * len((stems & desc_stems) - (exact & desc_toks))
    s += 1 * len((prefixes & slug_pre) - (stems & slug_stems))
    if prefixes & desc_pre:
        s += 1
    if slug.replace("-", " ") in prompt_l and len(slug) > 8:
        s += 8
    if proj_bands:
        proj_exact, _, _ = proj_bands
        s += min(2, len(proj_exact & slug_toks))
    if proj and entry["kind"] == "projects" and slug == proj:
        s += 6
    elif proj and proj in entry["path"].split("/"):
        s += 2
    if entry["kind"] == "sessions":
        s = int(s * 0.5)
    return s

def bm25(index, query_stems, k1=1.5, b=0.75, min_score=1.0):
    """Rank indexed notes by BM25 over the query stems. A note that only shares very common words
    (score under min_score) is left out, so a tiny vault does not match everything."""
    N = index["n"]
    avgdl = index["avgdl"] or 1.0
    scores = []
    for path, doc in index["docs"].items():
        dl = doc["len"]
        score = 0.0
        for term in query_stems:
            df = index["df"].get(term, 0)
            if df == 0:
                continue
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
            tf = doc["tf"].get(term, 0)
            denom = tf + k1 * (1 - b + b * dl / avgdl)
            score += idf * (tf * (k1 + 1)) / denom
        if score >= min_score:
            scores.append((path, score))
    scores.sort(key=lambda x: (-x[1], x[0]))
    return scores

def rrf(*ranked_lists, k=60):
    fused = {}
    for lst in ranked_lists:
        for rank, path in enumerate(lst, start=1):
            fused[path] = fused.get(path, 0.0) + 1.0 / (k + rank)
    return fused

def read_note(vault, path, budget):
    """Read a note's body. `path` may be absolute, or relative to the vault, with or without `.md`."""
    try:
        if not os.path.isabs(path):
            path = os.path.join(vault, path)
        if not path.endswith(".md") and not os.path.isfile(path):
            path = path + ".md"
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        txt = strip_frontmatter(txt)
        if len(txt) <= budget:
            return txt, False
        cut = txt.rfind("\n", 0, budget)
        if cut == -1:
            cut = budget
        return txt[:cut], True
    except Exception as e:
        log(f"read_note error: {e}")
        return None, False

def session_state_path(session_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:64] or "nosession"
    return os.path.join(STATE_DIR, "sessions", f"{safe}.json")

def load_session(session_id):
    path = session_state_path(session_id)
    default = {
        "session_id": session_id,
        "project": None,
        "start": None,
        "written": [],
        "shipped": [],
        "latched": [],
        "prompts": 0,
        "last_sweep": 0
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        default.update(data)
    except Exception:
        pass
    return default

def save_session(session_id, st):
    path = session_state_path(session_id)
    try:
        _ensure_dir(os.path.dirname(path))
        tmp = f"{path}.{os.getpid()}.tmp"  # unique per process: two hooks saving at once never share a temp file
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:
        log(f"save_session error: {e}")
        try:
            os.remove(tmp)
        except Exception:
            pass

class session_lock(object):
    """Exclusive lock on one session's state, for the hooks that run at the same moment on the same event
    (capture.py and rules.py both run on PostToolUse). `with session_lock(sid): ...`. Uses fcntl.flock; where
    that is missing it is a no-op, and a lock that cannot be taken within `timeout` seconds is skipped (logged)
    so a hook never hangs."""

    def __init__(self, session_id, timeout=3.0):
        self.path = session_state_path(session_id) + ".lock"
        self.timeout = timeout
        self.fh = None
        self.acquired = False  # True only while this process really holds the lock

    def __enter__(self):
        if fcntl is None:
            self.acquired = True  # no locking on this platform: best effort, as before
            return self
        try:
            _ensure_dir(os.path.dirname(self.path))
            self.fh = open(self.path, "a+")
            deadline = time.time() + self.timeout
            while True:
                try:
                    fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.acquired = True
                    return self
                except OSError:
                    if time.time() >= deadline:
                        # another hook has held it for too long: the caller must skip its write (fail open),
                        # never read-modify-write without owning the lock
                        log("session_lock: busy for %.1fs, this hook skips its state update" % self.timeout)
                        return self
                    time.sleep(0.01)
        except Exception as e:
            log(f"session_lock error: {e}")
            return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.fh is not None:
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
                self.fh.close()
        except Exception:
            pass
        return False

def update_session(session_id, fn):
    """Read-modify-write of the session state under the session lock. `fn(st)` edits the dict in place and may
    return False to say nothing changed (then nothing is written). Returns the state."""
    with session_lock(session_id) as lock:
        st = load_session(session_id)
        if not lock.acquired:
            return st  # could not own the state: read it, change nothing
        changed = fn(st)
        if changed is not False:
            save_session(session_id, st)
        return st

def latch(session_id, name):
    added = []

    def _add(st):
        if name in st["latched"]:
            return False
        st["latched"].append(name)
        added.append(name)
        return True

    update_session(session_id, _add)
    return bool(added)

def shipped_surfaces(cwd, vault):
    return [
        os.path.join(HOME, ".claude", "CLAUDE.md"),
        os.path.join(HOME, ".claude", "settings.json"),
        os.path.join(HOME, ".claude", "hooks"),
        os.path.join(cwd, ".claude"),
        os.path.join(cwd, "CLAUDE.md"),
        os.path.join(vault, "rules")
    ]

def is_under(path, root):
    try:
        return os.path.realpath(path).startswith(os.path.realpath(root) + os.sep)
    except Exception:
        return False

def session_tag(session_id):
    """The short tag of a session id used in file names and the `session:` frontmatter line: the first 8 hex
    characters of its SHA-1, so two ids that share a prefix never share a tag. '' when there is no id."""
    sid = (session_id or "").strip()
    if not sid:
        return ""
    return hashlib.sha1(sid.encode("utf-8")).hexdigest()[:8]

def in_progress_path(vault, project_slug, session_id=None):
    """The in-progress note of ONE session: `sessions/in-progress-<project>-<session tag>.md`, so two sessions on
    the same project never share (or delete) each other's capture. Without a session id: the old per-project name."""
    tag = session_tag(session_id)
    name = f"in-progress-{project_slug}-{tag}.md" if tag else f"in-progress-{project_slug}.md"
    return os.path.join(vault, "sessions", name)

def _dated_session_notes(vault, since_epoch):
    sess_dir = os.path.join(vault, "sessions")
    if not os.path.isdir(sess_dir):
        return []
    found = []
    for f in os.listdir(sess_dir):
        if not f.endswith(".md") or not re.match(r"^\d{4}-\d{2}-\d{2}-", f):
            continue
        p = os.path.join(sess_dir, f)
        try:
            if os.path.getmtime(p) >= since_epoch:
                found.append(p)
        except Exception:
            continue
    return found

def session_note_written_since(vault, since_epoch):
    """True when ANY dated session note changed since `since_epoch` (kept for old rules; the shipped gate uses
    session_note_for_session, which wants the note of THIS session)."""
    return bool(_dated_session_notes(vault, since_epoch))

def session_note_for_session(vault, session_id, since_epoch):
    """True when a dated session note changed since `since_epoch` names this session: the full session id anywhere
    in the note, or a `session: <tag>` line (the template's frontmatter field). A note from another session, or an
    edit to an old note, does not count."""
    sid = (session_id or "").strip()
    tag = session_tag(sid)
    if not sid or not tag:
        return False
    pat = re.compile(r"session:\s*" + re.escape(tag))
    for p in _dated_session_notes(vault, since_epoch):
        try:
            with open(p, "r", encoding="utf-8") as f:
                head = f.read(6000)
        except Exception:
            continue
        if sid in head or pat.search(head):
            return True
    return False

class RuleTimeout(BaseException):
    """Raised inside a rule that ran past its deadline. A BaseException so a rule's own `except Exception` cannot
    swallow it."""

def run_with_deadline(fn, seconds):
    """Run fn() and raise RuleTimeout if it is still going after `seconds`. Uses SIGALRM (an interval timer), so
    it only works on the main thread of a Unix process; anywhere else fn() just runs."""
    import signal
    import threading
    if seconds is None or seconds <= 0 or not hasattr(signal, "setitimer") \
            or threading.current_thread() is not threading.main_thread():
        return fn()

    def _alarm(signum, frame):
        raise RuleTimeout()

    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)

RULE_EVENT_RE = re.compile(r'^\s*EVENT\s*=\s*["\'](\w+)["\']', re.M)
RULE_IMPORT_BUDGET = 3.0   # seconds a rule file may take to import
RULE_CHECK_BUDGET = 5.0    # seconds one check() may take

def declared_event(path):
    """The EVENT a rule file declares (a literal string near the top), 'Stop' when it declares none. Read from the
    text so rules for OTHER events are never imported, and a broken Stop rule cannot touch PreToolUse."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(6000)
        m = RULE_EVENT_RE.search(head)
        return m.group(1) if m else "Stop"
    except Exception:
        return "Stop"

def _import_rule(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def rule_names(vault):
    """The rules that are on, by file name, without importing anything (for the boot line and listings)."""
    rules_dir = os.path.join(vault, "rules")
    if not os.path.isdir(rules_dir):
        return []
    off = set(load_config().get("rules_off", []))
    return sorted(fn[:-3] for fn in os.listdir(rules_dir)
                  if fn.endswith(".py") and not fn.startswith("_") and fn[:-3] not in off)

def load_rules(vault, event=None, import_budget=RULE_IMPORT_BUDGET, deadline=None):
    """Import the rule files in `<vault>/rules/`. With `event`, only the files that declare that EVENT are imported.
    Every import runs under its own deadline AND under `deadline` (an absolute time: the event's whole budget):
    once that is reached the remaining files are skipped and logged, so ten slow imports cannot add up to a
    stalled tool call. A file that raises anything (SystemExit included: an argparse call at module level does
    that) is logged and skipped, never allowed to block the hook."""
    rules_dir = os.path.join(vault, "rules")
    cfg = load_config()
    off = set(cfg.get("rules_off", []))
    loaded = []
    if not os.path.isdir(rules_dir):
        return loaded
    for fn in sorted(os.listdir(rules_dir)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        name = fn[:-3]
        if name in off:
            continue
        path = os.path.join(rules_dir, fn)
        if event and declared_event(path) != event:
            continue
        budget = import_budget
        if deadline is not None:
            left = deadline - time.time()
            if left <= 0.2:
                log(f"rule {name}: not imported, the rules' budget for this event is used up")
                continue
            budget = min(import_budget, left)
        try:
            mod = run_with_deadline(lambda: _import_rule(name, path), budget)
            mod.NAME = name
            doc = (mod.__doc__ or "").splitlines()[0] if mod.__doc__ else ""
            mod.DOC = doc.strip()
            mod.EVENT = getattr(mod, "EVENT", "Stop")
            mod.TOOLS = getattr(mod, "TOOLS", ".*")
            mod.ONCE = getattr(mod, "ONCE", True)
            if not hasattr(mod, "check") or not callable(mod.check):
                log(f"rule {name} missing check")
                continue
            loaded.append(mod)
        except RuleTimeout:
            log(f"rule {name}: import took over {budget:.1f}s, skipped")
        except (Exception, SystemExit) as e:
            log(f"load_rules error for {name}: {e!r}")
    return loaded

def today():
    return datetime.date.today().isoformat()

def hhmm_now():
    return datetime.datetime.now().strftime("%H:%M")

def short_path(path, cwd):
    if is_under(path, cwd):
        return os.path.relpath(path, cwd)
    if is_under(path, HOME):
        rel = os.path.relpath(path, HOME)
        return os.path.join("~", rel)
    return path
