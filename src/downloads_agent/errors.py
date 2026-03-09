"""Custom exception hierarchy for downloads-agent."""


class DownloadsAgentError(Exception):
    """Base exception for all downloads-agent errors."""


class ConfigError(DownloadsAgentError):
    """Invalid configuration."""


class LockError(DownloadsAgentError):
    """Lockfile contention — another instance is running."""
