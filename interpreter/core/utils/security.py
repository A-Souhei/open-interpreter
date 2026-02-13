"""
Security module for Open Interpreter.

Provides:
- Command whitelist/blocklist via CSV
- .gitignore-based file access restrictions
- Working directory enforcement
- Audit logging with auto-cleanup
- File permission hardening
"""

import csv
import datetime
import fnmatch
import json
import os
import re
import stat
import threading

_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CSV = os.path.join(_DIR, "default_blocked_commands.csv")

# ---------------------------------------------------------------------------
# 1. Command whitelist / blocklist
# ---------------------------------------------------------------------------

_blocked_commands = None
_lock = threading.Lock()


def _load_blocked_commands(csv_path=None):
    """Load blocked commands from a CSV file."""
    global _blocked_commands
    if csv_path is None:
        csv_path = _DEFAULT_CSV
    commands = []
    if os.path.isfile(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("type", "").strip().lower() == "blocked":
                    commands.append(row["command"].strip())
    _blocked_commands = commands
    return commands


def get_blocked_commands(csv_path=None):
    """Return the cached list of blocked commands, loading once if needed."""
    global _blocked_commands
    if _blocked_commands is None:
        with _lock:
            if _blocked_commands is None:
                _load_blocked_commands(csv_path)
    return _blocked_commands


def is_command_blocked(code, language="shell"):
    """
    Check whether *code* contains any blocked command pattern.
    Returns ``(True, matched_pattern)`` or ``(False, None)``.

    For pipe patterns like ``curl|bash``, each side is checked independently
    against the piped segments of the code.
    """
    blocked = get_blocked_commands()
    code_lower = code.lower().strip()
    for pattern in blocked:
        pattern_lower = pattern.lower().strip()
        # Handle pipe-based patterns: check if code pipes between the commands
        if "|" in pattern_lower:
            pat_parts = [p.strip() for p in pattern_lower.split("|")]
            code_parts = [p.strip() for p in re.split(r'\s*\|\s*', code_lower)]
            # Check if the pipe chain in the pattern exists in the code's pipe chain
            if len(pat_parts) == 2 and len(code_parts) >= 2:
                left_match = any(part.startswith(pat_parts[0]) for part in code_parts[:-1])
                right_match = any(part.startswith(pat_parts[1]) for part in code_parts[1:])
                if left_match and right_match:
                    return True, pattern
        # Simple substring match
        if pattern_lower in code_lower:
            return True, pattern
    return False, None


# ---------------------------------------------------------------------------
# 2. File-permission hardening helper
# ---------------------------------------------------------------------------


def set_owner_only(path):
    """Set file permissions to 0o600 (owner read/write only)."""
    if os.path.isfile(path):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


# ---------------------------------------------------------------------------
# 3. .gitignore-based file access guard
# ---------------------------------------------------------------------------


def _parse_gitignore(gitignore_path):
    """
    Parse a .gitignore file and return a list of patterns.
    Blank lines and comments are skipped.
    """
    patterns = []
    if not os.path.isfile(gitignore_path):
        return patterns
    with open(gitignore_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            patterns.append(line)
    return patterns


def _match_gitignore(rel_path, patterns):
    """Return True if *rel_path* matches any gitignore pattern."""
    for pattern in patterns:
        # Strip trailing slash for directory patterns
        pat = pattern.rstrip("/")
        if fnmatch.fnmatch(rel_path, pat):
            return True
        if fnmatch.fnmatch(os.path.basename(rel_path), pat):
            return True
        # Support patterns like dir/** matching dir/sub/file
        if pat.endswith("/**") and rel_path.startswith(pat[:-3]):
            return True
        if rel_path.startswith(pat + "/") or rel_path.startswith(pat):
            return True
    return False


class FileAccessGuard:
    """
    Restricts file access to a working directory and honours .gitignore.

    * Paths outside the working directory are blocked.
    * Paths matching a .gitignore pattern in the working directory are blocked.
    """

    def __init__(self, working_dir=None, enabled=True):
        self.enabled = enabled
        self.working_dir = os.path.abspath(working_dir) if working_dir else None
        self._gitignore_patterns = []
        if self.working_dir:
            gi = os.path.join(self.working_dir, ".gitignore")
            self._gitignore_patterns = _parse_gitignore(gi)

    def is_path_allowed(self, path):
        """Return ``(allowed: bool, reason: str)``."""
        if not self.enabled or self.working_dir is None:
            return True, ""

        abs_path = os.path.normcase(os.path.abspath(path))
        working_dir = os.path.normcase(self.working_dir)

        # Must be inside working directory
        if not abs_path.startswith(working_dir + os.sep) and abs_path != working_dir:
            return False, f"Path '{path}' is outside the allowed working directory."

        # Check .gitignore patterns
        rel = os.path.relpath(abs_path, self.working_dir)
        if self._gitignore_patterns and _match_gitignore(rel, self._gitignore_patterns):
            return False, f"Path '{path}' matches a .gitignore pattern and is blocked."

        return True, ""


# ---------------------------------------------------------------------------
# 4. Audit logging
# ---------------------------------------------------------------------------

_AUDIT_LOG_DIR = os.path.join(os.path.expanduser("~"), ".cache", "open-interpreter")
_AUDIT_LOG_FILE = os.path.join(_AUDIT_LOG_DIR, "audit.log")
_MAX_AGE_DAYS = 30


def _ensure_audit_dir():
    os.makedirs(_AUDIT_LOG_DIR, exist_ok=True)


def audit_log(event_type, details=""):
    """
    Append a line to the audit log.

    Format: ``ISO-8601-timestamp | event_type | details``
    """
    _ensure_audit_dir()
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    line = f"{ts} | {event_type} | {details}\n"
    fd = os.open(_AUDIT_LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def cleanup_audit_log(max_age_days=_MAX_AGE_DAYS):
    """Remove entries older than *max_age_days* from the audit log."""
    if not os.path.isfile(_AUDIT_LOG_FILE):
        return
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
    kept = []
    with open(_AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split("|", 1)
            if parts:
                try:
                    ts_str = parts[0].strip().replace("Z", "+00:00")
                    ts = datetime.datetime.fromisoformat(ts_str)
                    if ts >= cutoff:
                        kept.append(line)
                except (ValueError, IndexError):
                    kept.append(line)
    fd = os.open(_AUDIT_LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, "".join(kept).encode("utf-8"))
    finally:
        os.close(fd)
