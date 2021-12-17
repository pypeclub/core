"""Public API

Anything that isn't defined here is INTERNAL and unreliable for external use.

"""

from .pipeline import (
    ls,
    Creator,
    install,
    list_instances,
    remove_instance,
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
    maintained_selection
)

from .launch_logic import stub

__all__ = [
    # pipeline
    "ls",
    "Creator",
    "install",
    "list_instances",
    "remove_instance",
    "containerise",

    "file_extensions",
    "has_unsaved_changes",
    "save_file",
    "open_file",
    "current_file",
    "work_root",

    # lib
    "maintained_selection",
    # launch_logic
    "stub"
]
