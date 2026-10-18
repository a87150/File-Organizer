"""File Organizer desktop application."""

from .core import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SUCCESS,
    STATUS_UNDONE,
    Action,
    CleanupOptions,
    OrganizerEngine,
    OrganizeOptions,
    RenameOptions,
    SearchOptions,
)
from .duplicates import DuplicateGroup, DuplicateOptions, DuplicateResult, find_duplicates

__all__ = [
    "Action",
    "CleanupOptions",
    "DuplicateGroup",
    "DuplicateOptions",
    "DuplicateResult",
    "OrganizerEngine",
    "OrganizeOptions",
    "RenameOptions",
    "SearchOptions",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_SUCCESS",
    "STATUS_UNDONE",
    "find_duplicates",
]
