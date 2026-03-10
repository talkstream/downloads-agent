"""Exception hierarchy for downloads-agent.

Provides domain-specific exceptions that the CLI layer catches and converts
to user-friendly error messages with non-zero exit codes. Using a dedicated
hierarchy (rather than built-in exceptions) lets callers distinguish
recoverable agent errors from unexpected failures with a single except clause.

Hierarchy::

    DownloadsAgentError          # base for all agent errors
    ├── ConfigError              # YAML / validation problems
    └── LockError                # concurrent execution prevention
"""


class DownloadsAgentError(Exception):
    """Base exception for all downloads-agent errors.

    Caught at the CLI boundary to print a clean message and exit 1.
    All domain-specific exceptions inherit from this class so callers
    can handle agent errors uniformly.
    """


class ConfigError(DownloadsAgentError):
    """Configuration is missing, malformed, or fails validation.

    Raised during YAML loading (syntax errors, unreadable files) and
    during ``Config.__post_init__`` validation (invalid values, path
    conflicts, type mismatches).
    """


class LockError(DownloadsAgentError):
    """Lockfile contention — another instance is running.

    Raised by ``executor.acquire_lock()`` when the lockfile already exists
    and belongs to a live process, or when the lockfile content is
    unreadable. Prevents concurrent execution that could corrupt
    transaction logs or produce duplicate moves.
    """
