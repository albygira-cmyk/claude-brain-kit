#!/usr/bin/env python3
"""
brain.py: the command line for the BERNARD Brain Kit (init, map, check, status, doctor, rule, uninstall, version).
Run it as: python3 "<plugin folder>/bin/brain.py" <command>
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

# ----------------------------------------------------------------------
# Setup import path for shared library
# ----------------------------------------------------------------------
PLUGIN_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "hooks"))
import brainlib as lib  # noqa: E402

# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------


def _error(msg: str) -> None:
    """Print an error message and exit with status 1."""
    print(f"brain: {msg}", file=sys.stderr)
    sys.exit(1)


def _print(msg: str) -> None:
    """Print a message to stdout."""
    print(msg)


def _has_rules_runner() -> bool:
    """The free kit ships without hooks/rules.py; rule commands then explain instead of failing oddly."""
    return Path(PLUGIN_ROOT, "hooks", "rules.py").is_file()


def _expected_hooks() -> list:
    """The hook files this install's hooks.json really runs (the free kit runs fewer)."""
    try:
        text = Path(PLUGIN_ROOT, "hooks", "hooks.json").read_text(encoding="utf-8")
    except OSError:
        return ["boot.py", "route.py"]
    return [n for n in ("boot.py", "route.py", "capture.py", "rules.py") if n in text] or ["boot.py", "route.py"]


# ----------------------------------------------------------------------
# Command implementations
# ----------------------------------------------------------------------


def _owned_paths() -> list:
    """The paths uninstall removes on its own: a vault must never live inside one of them."""
    return [os.path.realpath(os.path.join(lib.BERNARD_DIR, name)) for name in PLUGIN_OWNED]


def _holds_vault(path: str, vault: str) -> bool:
    """True when `vault` is `path` or lives inside it (real paths, so symlinks cannot fool it)."""
    if not vault:
        return False
    real_vault = os.path.realpath(vault)
    real_path = os.path.realpath(path)
    return real_vault == real_path or lib.is_under(real_vault, real_path)


HOME_STANDARD_DIRS = {"Desktop", "Documents", "Downloads", "Library", "Pictures", "Movies", "Music", "Applications",
                      "Public", "Sites"}


def _too_broad_for_vault(vault: str) -> str:
    """Why `vault` can never be a vault (uninstall --remove-vault deletes the whole folder), or "" when it is fine:
    the disk root, the home folder or any folder above it, and the standard folders macOS keeps in the home folder."""
    if not vault:
        return ""
    real = os.path.realpath(vault)
    home = os.path.realpath(lib.HOME)
    if real == os.sep or real == home or lib.is_under(home, real):
        return "it is your home folder or a folder above it"
    if os.path.dirname(real) == home and os.path.basename(real) in HOME_STANDARD_DIRS:
        return f"it is your {os.path.basename(real)} folder"
    return ""


def cmd_init(args: argparse.Namespace) -> None:
    vault = Path(os.path.abspath(os.path.expanduser(args.vault))) if args.vault else Path(lib.vault_path())
    template_dir = Path(PLUGIN_ROOT) / "vault-template"

    if not template_dir.is_dir():
        _error("template directory missing")
    for owned in _owned_paths():
        if _holds_vault(owned, str(vault)):
            _error(f"the vault cannot live inside {owned}: that folder belongs to the plugin and is removed by "
                   f"uninstall. Pick another path, for example {os.path.join(lib.HOME, 'brain')}.")
    why = _too_broad_for_vault(str(vault))
    if why:
        _error(f"the vault cannot be {vault}: {why}, and uninstall --remove-vault would delete all of it. "
               f"Pick a folder of its own, for example {os.path.join(lib.HOME, 'brain')}.")

    copied = kept = 0
    for src in template_dir.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(template_dir)
        dst = vault / rel
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Determine if we may overwrite
        overwrite = False
        if args.force and rel.parts[0] in ("templates", "rules"):
            if rel == Path("rules/README.md") or rel.parts[0] == "templates":
                overwrite = True

        if dst.exists() and not overwrite:
            kept += 1
            continue

        shutil.copy2(src, dst)
        copied += 1

    # Save config
    cfg = lib.load_config()
    cfg["vault"] = str(vault)
    lib.save_config(cfg)

    # A MAP.md the user wrote (an existing Obsidian vault) is moved aside, never overwritten by the generated one
    user_map = vault / lib.MAP_NAME
    moved_map = None
    if user_map.is_file():
        try:
            mine = "*Generated by `brain map`." in user_map.read_text(encoding="utf-8", errors="replace")
        except OSError:
            mine = False
        if not mine:
            moved_map = vault / f"map-before-bernard-{time.strftime('%Y%m%d-%H%M%S')}.md"
            user_map.rename(moved_map)

    # Build map
    n = _locked_build_map(str(vault))
    if n is None:
        _error("another Claude session is rebuilding the map right now: run init again in a minute")

    # List rule names
    rules = sorted(p.stem for p in (vault / "rules").glob("*.py") if not p.name.startswith("_")) if (vault / "rules").is_dir() else []
    rules_str = ", ".join(rules) if rules else "none"

    _print(f"Brain ready at {vault}")
    _print(f"  {copied} files added, {kept} already there, {n} notes in the map, rules on: {rules_str}")
    if moved_map:
        _print(f"  Your own MAP.md was kept as {moved_map.name} (the brain writes its own MAP.md).")
    _print("  Next: start a new Claude Code session. The first lines of context will say \"BERNARD brain: on\".")
    _print(f"  Optional: open {vault} in Obsidian to browse it.")


def _locked_build_map(vault: str):
    """build_map under the same per-vault lock the hooks use (ensure_map), so a CLI rebuild never interleaves with a
    session's rebuild. Waits up to 30 s; returns None when the lock stayed busy."""
    with lib.map_lock(vault, timeout=30.0) as lk:
        if not lk.acquired:
            return None
        return lib.build_map(vault)


def cmd_map(_args: argparse.Namespace) -> None:
    vault = lib.vault_path()
    n = _locked_build_map(vault)
    if n is None:
        _error("another Claude session is rebuilding the map right now: try again in a minute")
    _print(f"MAP.md rebuilt: {n} notes indexed ({vault}/MAP.md)")


def _report(title: str, items: list) -> None:
    _print(f"{title}: {len(items)}")
    for item in items[:20]:
        _print(f"  {item}")
    if len(items) > 20:
        _print(f"  ... and {len(items) - 20} more")


def cmd_check(_args: argparse.Namespace) -> None:
    """Report notes the router will struggle with: bad names, near-empty bodies, no first sentence, dead links."""
    vault = lib.vault_path()
    if not lib.vault_exists(vault):
        _error(f"no vault at {vault} (run init first)")
    notes = lib.list_notes(vault)
    bad_names, short_bodies, no_sentence, broken_links = [], [], [], []
    existing = {rel for rel, _ in notes}
    link_re = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
    for rel, abs_path in notes:
        name = os.path.basename(rel)
        if re.search(r"[A-Z _]", name):
            bad_names.append(f"{rel}.md  (use lowercase-hyphenated: {lib.slugify(name)}.md)")
        try:
            text = Path(abs_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = lib.strip_frontmatter(text).strip()
        if len(body) < 40:
            short_bodies.append(f"{rel}.md  ({len(body)} characters)")
        if not lib.first_sentence(text):
            no_sentence.append(f"{rel}.md  (add one plain sentence under the title)")
        # links inside code (an example in backticks or a fenced block) are not real links
        prose = re.sub(r"```.*?```", "", body, flags=re.S)
        prose = re.sub(r"`[^`\n]*`", "", prose)
        for target in link_re.findall(prose):
            target = target.strip().rstrip("/")
            if target.endswith(".md"):
                target = target[:-3]
            if target and target not in existing and not os.path.isfile(os.path.join(vault, target + ".md")):
                broken_links.append(f"{rel}.md -> [[{target}]]")
    _report("Filenames with uppercase, spaces or underscores", bad_names)
    _report("Notes with a body under 40 characters", short_bodies)
    _report("Notes with no first sentence (the map shows nothing for them)", no_sentence)
    _report("Wikilinks whose target does not exist", broken_links)
    total = len(bad_names) + len(short_bodies) + len(no_sentence) + len(broken_links)
    _print("No issues found." if total == 0 else f"{total} issue(s) in {len(notes)} notes.")
    sys.exit(1 if (bad_names or short_bodies) else 0)


def cmd_status(_args: argparse.Namespace) -> None:
    vault = lib.vault_path()
    exists = lib.vault_exists(vault)
    note_counts = {}
    for rel, _ in lib.list_notes(vault) if exists else []:
        kind = rel.split("/", 1)[0]
        note_counts[kind] = note_counts.get(kind, 0) + 1
    _print(f"Vault: {vault} ({'exists' if exists else 'missing: run init'})")
    for kind in lib.NOTE_DIRS + sorted(k for k in note_counts if k not in lib.NOTE_DIRS):
        if kind in note_counts:
            _print(f"  {kind}: {note_counts[kind]}")
    _print(f"Map fresh: {'yes' if exists and not lib.map_is_stale(vault) else 'no'}")
    if not _has_rules_runner():
        _print("Rules: not in this kit (the full kit adds rule hooks)")
    else:
        rules = lib.load_rules(vault) if exists else []
        if rules:
            _print("Rules:")
            for r in rules:
                _print(f"  {r.NAME} — {r.EVENT} — {r.DOC}")
        else:
            _print("Rules: (none)")
    _print(f"Config: {lib.CONFIG}")
    _print(f"State folder: {lib.STATE_DIR}")
    _print(f"Plugin root: {PLUGIN_ROOT}")
    _print(f"Python: {sys.version.split()[0]}")


def cmd_doctor(_args: argparse.Namespace) -> None:
    py_ok = sys.version_info >= (3, 8)
    _print(f"{'OK' if py_ok else 'FIX'} Python {sys.version.split()[0]} (3.8 or newer needed)")

    for name in _expected_hooks():
        path = Path(PLUGIN_ROOT, "hooks", name)
        _print(f"{'OK' if path.is_file() else 'FIX'} hooks/{name} present")

    vault = lib.vault_path()
    vault_ok = lib.vault_exists(vault)
    _print(f"{'OK' if vault_ok else 'FIX'} vault at {vault}" + ("" if vault_ok else "  (run: brain.py init)"))

    if vault_ok:
        _print(f"{'OK' if not lib.map_is_stale(vault) else 'FIX'} map fresh" + ("" if not lib.map_is_stale(vault) else "  (run: brain.py map)"))
        if _has_rules_runner():
            rules_dir = Path(vault, "rules")
            files = sorted(p.stem for p in rules_dir.glob("*.py") if not p.name.startswith("_")) if rules_dir.is_dir() else []
            off = set(lib.load_config().get("rules_off", []))
            loaded = {r.NAME for r in lib.load_rules(vault)}
            for stem in files:
                if stem in off:
                    _print(f"OK rule {stem} (turned off in config)")
                elif stem in loaded:
                    _print(f"OK rule {stem} imports")
                else:
                    _print(f"FIX rule {stem} does not import or has no check(): see {lib.LOG}")

    installed = False
    try:
        installed_path = Path(lib.HOME, ".claude", "plugins", "installed_plugins.json")
        if installed_path.is_file():
            data = json.loads(installed_path.read_text(encoding="utf-8"))
            plugins = data.get("plugins", {})
            keys = plugins.keys() if isinstance(plugins, dict) else [p.get("name", "") for p in plugins]
            installed = any(str(k).startswith("bernard@") or str(k) == "bernard" for k in keys)
    except Exception:
        pass
    _print("OK plugin installed in Claude Code" if installed else "FIX plugin not installed: run install.sh (fine if you use --plugin-dir)")
    sys.exit(0)


RULE_TEMPLATE = '''"""TODO: one sentence saying what this rule enforces."""

EVENT = "{event}"   # "Stop" (before Claude finishes a turn), "PreToolUse" (before a tool runs), "PostToolUse" (after)
TOOLS = "{tools}"   # tool events only: a regex matched against the tool name, e.g. "Write|Edit|MultiEdit|Bash"
ONCE = {once}       # True: block once per session, then let it pass. False: block every time.


def check(payload, ctx):
    """Return a plain-language message to block (what was wrong and what to do instead), or None to pass."""
    # payload is the hook JSON Claude Code sent; ctx has vault, session, cwd, now, today, lib (see rules/README.md)
    # Example: block a tool call on one file
    #   path = (payload.get("tool_input") or {{}}).get("file_path") or ""
    #   if path.endswith("package-lock.json"):
    #       return f"{{path}} is generated. Run the package manager instead of editing it."
    # Example: block the end of a turn when this session changed something
    #   if ctx["session"]["written"] and not some_condition:
    #       return "This session changed files but ... Do X before finishing."
    return None
'''


def cmd_rule(args: argparse.Namespace) -> None:
    vault = lib.vault_path()
    if not _has_rules_runner():
        _error("rules are part of the full kit; this install has no rule hooks")
    if not lib.vault_exists(vault):
        _error(f"no vault at {vault} (run init first)")
    if args.subcmd == "list":
        rules = lib.load_rules(vault)
        if not rules:
            _print("(no rules)")
            return
        for r in rules:
            name = getattr(r, "NAME", r.__name__)
            event = getattr(r, "EVENT", "")
            tools = getattr(r, "TOOLS", "")
            once = getattr(r, "ONCE", "")
            doc = getattr(r, "DOC", "")
            _print(f"{name}  {event}  tools={tools}  once={once}  {doc}")

    elif args.subcmd == "new":
        name = args.name
        slug = lib.slugify(name)
        dst = Path(vault, "rules", f"{slug}.py")
        if dst.exists():
            _error(f"rule file already exists: {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        template = RULE_TEMPLATE.format(event=args.event, tools=args.tools, once=str(not args.every_time))
        dst.write_text(template, encoding="utf-8")
        _print(f"Created rule file: {dst}")
        _print(f'Edit check(), then test it: python3 "{PLUGIN_ROOT}/bin/brain.py" rule test {slug} --tool Write --file some/path')

    elif args.subcmd == "test":
        name = args.name
        slug = lib.slugify(name)
        rules = lib.load_rules(vault)
        rule_mod = None
        for r in rules:
            if getattr(r, "NAME", r.__name__) == slug:
                rule_mod = r
                break
        if not rule_mod:
            _error(f"rule not found: {name}")

        # Build payload
        if args.payload:
            try:
                payload = json.loads(Path(args.payload).read_text())
            except Exception:
                _error("cannot read payload file")
        else:
            payload = {
                "hook_event_name": getattr(rule_mod, "EVENT", ""),
                "session_id": "rule-test",
                "cwd": args.cwd or os.getcwd(),
                "tool_name": args.tool or "",
                "tool_input": {}
            }
            if args.file:
                payload["tool_input"]["file_path"] = args.file
            if args.command:
                payload["tool_input"]["command"] = args.command

        # Build ctx the same way hooks/rules.py does
        sid = payload.get("session_id", "rule-test")
        cwd = payload.get("cwd") or os.getcwd()
        st = lib.load_session(sid)
        ctx = {
            "event": getattr(rule_mod, "EVENT", ""),
            "vault": vault,
            "state_dir": lib.STATE_DIR,
            "session_id": sid,
            "cwd": cwd,
            "session": st,
            "home": lib.HOME,
            "plugin_root": PLUGIN_ROOT,
            "now": time.time(),
            "today": lib.today(),
            "tool_name": payload.get("tool_name", ""),
            "tool_input": payload.get("tool_input", {}),
            "in_progress_path": lib.in_progress_path(vault, st.get("project") or lib.project_hint(cwd), sid),
            "lib": lib,
        }

        try:
            msg = rule_mod.check(payload, ctx)
        except Exception as e:
            _error(f"rule crashed: {e}")

        if msg:
            _print(f"BLOCKS: {msg}")
            sys.exit(2)
        else:
            _print("PASSES")
            sys.exit(0)


PLUGIN_OWNED = ["state", "config.json", "config.json.tmp", "log.txt"]  # what uninstall may delete on its own


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Remove what the plugin owns (state, config, log). The vault - the user's notes - is deleted only with
    --remove-vault --yes, wherever it lives, even inside the plugin's own folder."""
    vault = lib.vault_path()  # read before the config goes
    if args.remove_vault and not args.yes:
        _print(f"Vault path: {vault}")
        _print("Nothing was removed. Add --yes to confirm deleting the vault and its notes.")
        sys.exit(1)

    bernard_dir = lib.BERNARD_DIR
    remove_vault = bool(args.remove_vault and args.yes)
    why = _too_broad_for_vault(vault) if remove_vault else ""
    if why:
        # an older install (or a hand-edited config) can point the vault at the home folder: never delete that
        _print(f"Vault NOT removed: {vault} is not a folder of its own ({why}). Delete the notes by hand if you mean it.")
        remove_vault = False
    if remove_vault:
        # the vault goes first, wherever it is, so nothing below can be left half-deleted
        shutil.rmtree(vault, ignore_errors=True)
    for name in PLUGIN_OWNED:
        p = os.path.join(bernard_dir, name)
        if not remove_vault and _holds_vault(p, vault) and os.path.exists(vault):
            # the vault was put inside a plugin-owned folder (init now refuses that; an older install may have it):
            # the notes win, the folder stays
            _print(f"{p} left alone: it holds your vault ({vault})")
            continue
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.lexists(p):
                os.remove(p)
        except Exception as e:
            _print(f"could not remove {p}: {e}")
    try:
        if os.path.isdir(bernard_dir) and not os.listdir(bernard_dir):
            os.rmdir(bernard_dir)
            _print(f"Bernard's own folder removed: {bernard_dir}")
        elif os.path.isdir(bernard_dir):
            _print(f"Bernard's state, config and log removed from {bernard_dir} (the folder still holds other files, left alone)")
    except Exception as e:
        _print(f"could not remove {bernard_dir}: {e}")

    if remove_vault:
        if os.path.exists(vault):
            _print(f"Vault NOT fully removed (check permissions): {vault}")
        else:
            _print(f"Vault removed: {vault}")
    elif os.path.isdir(vault):
        _print(f"Your notes are still at {vault}")
    else:
        _print(f"No vault folder found at {vault} (nothing to keep)")

    _print("To remove the plugin itself, run:")
    _print("  claude plugin uninstall bernard@bernard-brain-kit")
    _print("  claude plugin marketplace remove bernard-brain-kit")


def cmd_version(_args: argparse.Namespace) -> None:
    plugin_json = Path(PLUGIN_ROOT, ".claude-plugin", "plugin.json")
    try:
        data = json.loads(plugin_json.read_text())
        version = data.get("version", "unknown")
    except Exception:
        version = "unknown"
    _print(f"BERNARD Brain Kit {version}")


# ----------------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain", description="BERNARD Brain Kit CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="initialise the vault")
    p_init.add_argument("--vault", help="path to vault")
    p_init.add_argument("--force", action="store_true", help="overwrite templates and rules README")
    p_init.set_defaults(func=cmd_init)

    # map
    p_map = sub.add_parser("map", help="rebuild MAP.md")
    p_map.set_defaults(func=cmd_map)

    # check
    p_check = sub.add_parser("check", help="run sanity checks on notes")
    p_check.set_defaults(func=cmd_check)

    # status
    p_status = sub.add_parser("status", help="show current status")
    p_status.set_defaults(func=cmd_status)

    # doctor
    p_doctor = sub.add_parser("doctor", help="diagnose common problems")
    p_doctor.set_defaults(func=cmd_doctor)

    # rule
    p_rule = sub.add_parser("rule", help="manage rules")
    rule_sub = p_rule.add_subparsers(dest="subcmd", required=True)

    p_rule_list = rule_sub.add_parser("list", help="list rules")
    p_rule_list.set_defaults(func=cmd_rule)

    p_rule_new = rule_sub.add_parser("new", help="create a new rule")
    p_rule_new.add_argument("name", help="rule name")
    p_rule_new.add_argument("--event", default="Stop", choices=["Stop", "PreToolUse", "PostToolUse"])
    p_rule_new.add_argument("--tools", default=".*", help="tool events only: regex matched against the tool name")
    p_rule_new.add_argument("--every-time", action="store_true", default=False,
                            help="block every time it matches (default: once per session)")
    p_rule_new.set_defaults(func=cmd_rule)

    p_rule_test = rule_sub.add_parser("test", help="test a rule")
    p_rule_test.add_argument("name", help="rule name")
    p_rule_test.add_argument("--payload", help="JSON file with payload")
    p_rule_test.add_argument("--tool", help="tool name")
    p_rule_test.add_argument("--file", help="file path for tool input")
    p_rule_test.add_argument("--command", help="command string for tool input")
    p_rule_test.add_argument("--cwd", help="current working directory")
    p_rule_test.set_defaults(func=cmd_rule)

    # uninstall
    p_uninstall = sub.add_parser("uninstall", help="remove Bernard data")
    p_uninstall.add_argument("--remove-vault", action="store_true", help="also delete the vault")
    p_uninstall.add_argument("--yes", action="store_true", help="confirm vault deletion")
    p_uninstall.set_defaults(func=cmd_uninstall)

    # version
    p_version = sub.add_parser("version", help="show version")
    p_version.set_defaults(func=cmd_version)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        _error(str(e))


if __name__ == "__main__":
    main()
