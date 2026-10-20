"""File Organizer desktop application."""

__version__ = "1.2.5"

from .core import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SUCCESS,
    STATUS_UNDONE,
    Action,
    ActionStatus,
    CleanupOptions,
    FileEntry,
    OrganizerEngine,
    OrganizeOptions,
    RenameOptions,
    SearchOptions,
)
from .duplicates import DuplicateGroup, DuplicateOptions, DuplicateResult, find_duplicates

__all__ = [
    "Action",
    "ActionStatus",
    "CleanupOptions",
    "DuplicateGroup",
    "DuplicateOptions",
    "DuplicateResult",
    "FileEntry",
    "OrganizerEngine",
    "OrganizeOptions",
    "RenameOptions",
    "SearchOptions",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_SUCCESS",
    "STATUS_UNDONE",
    "__version__",
    "find_duplicates",
]
