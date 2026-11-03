#!/usr/bin/env python3
"""SessionStart hook: tell Claude the brain is on, where the vault is, how to use it, which rules run,
and show the current project note and the latest session note (2,500 characters at most)."""
from __future__ import annotations
import os
import re
import sys
import time

# Ensure brainlib is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brainlib as lib  # noqa: E402

BOOT_CAP = 2500


def _cut_to_limit(text: str, limit: int) -> str:
    """Return text truncated to at most limit characters."""
    return text[:limit]


def _load_project_excerpt(vault: str, slug: str) -> str:
    """Return first 700 chars of the project note body, or empty string."""
    path = os.path.join(vault, "projects", f"{slug}.md")
    if not os.path.isfile(path):
        return ""
    body, _ = lib.read_note(vault, path, 700)
    return (body or "").strip()


def _latest_session_note(vault: str) -> tuple[str, str]:
    """Return (rel_path, excerpt) of newest dated session note, or ('', '')."""
    sessions_dir = os.path.join(vault, "sessions")
    if not os.path.isdir(sessions_dir):
        return "", ""
    candidates = []
    for name in os.listdir(sessions_dir):
        if not name.lower().endswith(".md"):
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}-", name):
            continue
        full = os.path.join(sessions_dir, name)
        try:
            mtime = os.path.getmtime(full)
        except OSError:
            continue
        candidates.append((mtime, name, full))
    if not candidates:
        return "", ""
    _, rel_name, full_path = max(candidates)
    rel_path = os.path.relpath(full_path, vault)
    body, _ = lib.read_note(vault, full_path, 500)
    return rel_path, (body or "").strip()


def _note_counts(vault: str) -> dict:
    """Return dict kind->count from lib.list_notes."""
    counts = {}
    for rel_path, _abs in lib.list_notes(vault):
        kind = rel_path.split("/", 1)[0]
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _has_rules_runner() -> bool:
    """The free kit ships without hooks/rules.py; then rules are not part of this install."""
    return os.path.isfile(os.path.join(lib.PLUGIN_ROOT, "hooks", "rules.py"))


def _format_rules(vault: str) -> str:
    if not _has_rules_runner():
        return "none (rule hooks are part of the full kit)"
    names = lib.rule_names(vault)  # by file name: boot never imports rule code, so a slow rule cannot slow boot
    return ", ".join(names) if names else "none"


def _skills_line() -> str:
    """List only the skills this install really has (the free kit has fewer)."""
    skills_dir = os.path.join(lib.PLUGIN_ROOT, "skills")
    names = []
    for want in ("save", "rule", "find", "setup"):
        if os.path.isfile(os.path.join(skills_dir, want, "SKILL.md")):
            names.append(f"/bernard:{want}")
    return ", ".join(names) if names else "none"


def main() -> None:
    try:
        d = lib.read_stdin_json()
        sid = d.get("session_id", "")
        cwd = d.get("cwd") or os.getcwd()
        vault = lib.vault_path()

        if not lib.vault_exists(vault):
            msg = (
                "# BERNARD brain: not set up yet\n"
                f"No vault at {vault}. To turn memory on, use the skill /bernard:setup, "
                f"or run: python3 \"{lib.PLUGIN_ROOT}/bin/brain.py\" init\n"
                "Until then this plugin changes nothing."
            )
            lib.emit("SessionStart", msg)
            return

        lib.ensure_map(vault)
        def _begin(s):
            if s.get("start") is not None:
                return False
            s["start"] = time.time()
            s["project"] = lib.project_hint(cwd)
            return True
        st = lib.update_session(sid, _begin)

        # Build header
        counts = _note_counts(vault)
        total_notes = sum(counts.values())
        kind_parts = []
        for kind in ["topics", "patterns", "references", "projects", "sessions"]:
            if kind in counts:
                kind_parts.append(f"{counts[kind]} {kind}")
        kind_summary = ", ".join(kind_parts)

        header = (
            "# BERNARD brain: on\n"
            f"Vault: {vault} ({total_notes} notes: {kind_summary}). "
            f"Map: {os.path.join(vault, 'MAP.md')}. "
            f"CLI: python3 \"{lib.PLUGIN_ROOT}/bin/brain.py\"\n"
            "Each prompt arrives with a \"BERNARD ROUTE\" packet: the notes that match it. "
            "Before acting on a substantive task, name the one note that applies and what it changes about your approach, or say that none applies. Never claim a note was read unless it was in the packet or you opened it.\n"
            "New knowledge goes into the vault: topics/<domain>/ (what is true), patterns/<domain>/ (how to do it), references/<domain>/ (a digested source), projects/ (one per project), sessions/ (one per work session). Filenames lowercase-hyphenated, 2+ words. Every note opens with one plain sentence saying what it is for; the map shows that sentence. "
            f"Skills: {_skills_line()}.\n"
            f"Rules on: {_format_rules(vault)}\n"
        )

        # Project note excerpt
        proj_slug = lib.project_hint(cwd)
        proj_excerpt = _load_project_excerpt(vault, proj_slug)
        proj_section = ""
        if proj_excerpt:
            proj_section = f"## Project note: projects/{proj_slug}.md\n{proj_excerpt}\n"

        # Latest session note excerpt
        sess_rel, sess_excerpt = _latest_session_note(vault)
        sess_section = ""
        if sess_excerpt:
            sess_section = f"## Latest session: {sess_rel}\n{sess_excerpt}\n"

        # Assemble full text, respecting the cap: cut the two excerpts first
        full_text = header + proj_section + sess_section
        if len(full_text) > BOOT_CAP:
            excess = len(full_text) - BOOT_CAP
            # Reduce project excerpt
            if proj_excerpt:
                cut = min(excess, len(proj_excerpt))
                proj_excerpt = proj_excerpt[: len(proj_excerpt) - cut]
                excess -= cut
                proj_section = f"## Project note: projects/{proj_slug}.md\n{proj_excerpt}\n"
            # Reduce session excerpt if still over
            if excess > 0 and sess_excerpt:
                cut = min(excess, len(sess_excerpt))
                sess_excerpt = sess_excerpt[: len(sess_excerpt) - cut]
                sess_section = f"## Latest session: {sess_rel}\n{sess_excerpt}\n"
            full_text = header + proj_section + sess_section
            # Final hard cut
            full_text = _cut_to_limit(full_text, BOOT_CAP)

        lib.emit("SessionStart", full_text)
    except Exception as e:
        lib.log(f"boot.py error: {repr(e)}")
        # Emit nothing, exit cleanly: a broken boot must never break the session
        return

if __name__ == "__main__":
    main()
