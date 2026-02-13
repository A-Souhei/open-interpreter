"""
Security module for Open Interpreter.

Provides:
- Command whitelist/blocklist via CSV
- .gitignore-based file access restrictions
- Working directory enforcement
- Audit logging with auto-cleanup
- File permission hardening

**Note:** Command blocking uses pattern matching and is intended as
defense-in-depth.  It will catch common dangerous commands but cannot
prevent all possible obfuscation techniques (e.g. shell variable
expansion, command substitution, encoding tricks).  Always review code
before execution when ``auto_run`` is disabled.
"""

import csv
import datetime
import fcntl
import fnmatch
import os
import re
import stat
import sys
import threading

_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CSV = os.path.join(_DIR, "default_blocked_commands.csv")

# ---------------------------------------------------------------------------
# 1. Command whitelist / blocklist
# ---------------------------------------------------------------------------

_blocked_commands = None
_lock = threading.Lock()


def _load_blocked_commands(csv_path=None):
    """Load blocked commands from a CSV file.

    The CSV must contain ``command`` and ``type`` columns.
    Rows with ``type`` equal to ``blocked`` are loaded.
    """
    global _blocked_commands
    if csv_path is None:
        csv_path = _DEFAULT_CSV
    commands = []
    if os.path.isfile(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None or "command" not in reader.fieldnames or "type" not in reader.fieldnames:
                print(
                    f"Warning: blocked commands CSV '{csv_path}' is missing required "
                    f"'command' and/or 'type' columns. No commands loaded.",
                    file=sys.stderr,
                )
                _blocked_commands = commands
                return commands
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

    For pipe patterns like ``curl|bash``, the left pattern must appear in an
    earlier pipe stage than the right pattern.

    **Note:** This is a defense-in-depth measure using pattern matching.
    It cannot catch all possible obfuscation (shell variables, command
    substitution, encoding, etc.).  All languages are checked against the
    same pattern list; shell-specific patterns may not be meaningful for
    other languages but are checked as an extra safety layer.
    """
    blocked = get_blocked_commands()
    code_lower = code.lower().strip()
    for pattern in blocked:
        pattern_lower = pattern.lower().strip()
        # Handle pipe-based patterns: ensure left appears before right
        if "|" in pattern_lower:
            pat_parts = [p.strip() for p in pattern_lower.split("|")]
            code_parts = [p.strip() for p in re.split(r'\s*\|\s*', code_lower)]
            if len(pat_parts) == 2 and len(code_parts) >= 2:
                for i in range(len(code_parts) - 1):
                    if code_parts[i].startswith(pat_parts[0]):
                        for j in range(i + 1, len(code_parts)):
                            if code_parts[j].startswith(pat_parts[1]):
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
    """
    Return True if *rel_path* is ignored according to the given gitignore
    patterns.

    Patterns are evaluated in order.  Later matches override earlier ones
    and negation patterns (starting with ``!``) are supported.
    """
    ignored = False
    for pattern in patterns:
        is_negation = pattern.startswith("!")
        raw_pat = pattern[1:] if is_negation else pattern
        # Strip trailing slash for directory patterns
        pat = raw_pat.rstrip("/")

        matched = False
        if fnmatch.fnmatch(rel_path, pat):
            matched = True
        elif fnmatch.fnmatch(os.path.basename(rel_path), pat):
            matched = True
        # Support patterns like dir/** matching dir/sub/file
        elif pat.endswith("/**") and rel_path.startswith(pat[:-3]):
            matched = True
        # Exact directory prefix match (avoid over-broad prefix matching)
        elif rel_path == pat or rel_path.startswith(pat + "/"):
            matched = True

        if matched:
            ignored = not is_negation

    return ignored


class FileAccessGuard:
    """
    Restricts file access to a working directory and honours .gitignore.

    * Paths outside the working directory are blocked.
    * Paths matching a .gitignore pattern in the working directory are blocked.
    * Symlinks are resolved before checking so they cannot escape the boundary.

    **Note:** The guard is disabled by default (``enabled=False``) when no
    working directory has been configured.  Call
    :meth:`Files.set_working_directory` to enable it.
    """

    def __init__(self, working_dir=None, enabled=True):
        self.enabled = enabled
        self.working_dir = os.path.abspath(working_dir) if working_dir else None
        self._gitignore_patterns = []
        if self.working_dir:
            gi = os.path.join(self.working_dir, ".gitignore")
            self._gitignore_patterns = _parse_gitignore(gi)
            ai = os.path.join(self.working_dir, ".ai-ignore")
            self._gitignore_patterns.extend(_parse_gitignore(ai))

    def is_path_allowed(self, path):
        """Return ``(allowed: bool, reason: str)``."""
        if not self.enabled or self.working_dir is None:
            return True, ""

        # Resolve symlinks before enforcing boundary
        abs_path = os.path.normcase(os.path.realpath(path))
        working_dir = os.path.normcase(os.path.realpath(self.working_dir))

        # Must be inside working directory
        try:
            common = os.path.commonpath([working_dir, abs_path])
        except ValueError:
            return False, f"Path '{path}' is outside the allowed working directory."

        if common != working_dir:
            return False, f"Path '{path}' is outside the allowed working directory."

        # Check .gitignore patterns
        rel = os.path.normcase(os.path.relpath(abs_path, working_dir))
        if self._gitignore_patterns and _match_gitignore(rel, self._gitignore_patterns):
            return False, f"Path '{path}' matches a .gitignore pattern and is blocked."

        return True, ""

    def get_protected_patterns_text(self):
        """Return a human-readable description of protected patterns."""
        if not self._gitignore_patterns:
            return ""
        lines = []
        for p in self._gitignore_patterns:
            if not p.startswith("!"):
                lines.append(f"  - {p}")
        return "\n".join(lines)


def check_code_for_protected_access(code, guard):
    """
    Check whether *code* references files or directories protected by *guard*.

    Returns ``(True, reason)`` when a protected reference is found, or
    ``(False, "")`` otherwise.

    **Note:** This is a defense-in-depth heuristic.  It checks for common
    patterns but cannot catch every possible obfuscation.
    """
    if not guard or not guard.enabled or not guard._gitignore_patterns:
        return False, ""

    for pattern in guard._gitignore_patterns:
        if pattern.startswith("!"):
            continue
        clean = pattern.rstrip("/")
        if not clean:
            continue
        # Wildcard patterns like *.key → look for the extension
        if clean.startswith("*"):
            suffix = clean[1:]  # e.g. ".key"
            if suffix and suffix in code:
                return True, f"Code references protected pattern '{pattern}'"
        else:
            if clean in code:
                return True, f"Code references protected file/directory '{pattern}'"

    return False, ""


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

    Errors during logging are printed to *stderr* so that callers are
    aware of audit failures.
    """
    try:
        _ensure_audit_dir()
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        line = f"{ts} | {event_type} | {details}\n"
        fd = os.open(_AUDIT_LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except OSError as e:
        print(f"Warning: failed to write audit log: {e}", file=sys.stderr)


def cleanup_audit_log(max_age_days=_MAX_AGE_DAYS):
    """Remove entries older than *max_age_days* from the audit log.

    Uses ``fcntl.flock`` to prevent concurrent modifications.
    """
    if not os.path.isfile(_AUDIT_LOG_FILE):
        return
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
    fd = os.open(_AUDIT_LOG_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with os.fdopen(os.dup(fd), "r", encoding="utf-8") as f:
            kept = []
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
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, "".join(kept).encode("utf-8"))
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
