"""Public API

Anything that isn't defined here is INTERNAL and unreliable for external use.

"""

from .pipeline import (
    ls,
    list_instances,
    remove_instance,
    Creator,
    install,
    containerise
)

from .workio import (
    file_extensions,
    has_unsaved_changes,
    save_file,
    open_file,
    current_file,
    work_root,
)

from .lib import (
    launch,
    stub,
    maintained_selection,
    maintained_visibility,
    show,
    execute_in_main_thread
)

__all__ = [
    # pipeline
    "ls",
    "list_instances",
    "remove_instance",
    "Creator",
    "install",
    "containerise",

    # workfiles
    "file_extensions",
    "has_unsaved_changes",
    "save_file",
    "open_file",
    "current_file",
    "work_root",

    # lib
    "launch",
    "stub",
    "maintained_selection",
    "maintained_visibility",
    "show",
    "execute_in_main_thread"
]
