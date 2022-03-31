"""Public application programming interface

The following members are public and reliable.
That is to say, anything **not** defined here is **internal**
and likely **unreliable** for use outside of the codebase itself.

|
|

"""

from . import schema
from . mongodb import (
    AvalonMongoDB,
    session_data_from_environment
)
from .pipeline import (
    install,
    uninstall,

    Session,

    # Deprecated
    Session as session,

    publish,

    data,

    register_root,
    register_host,

    registered_host,
    registered_config,
    registered_root,
)


__all__ = [
    "AvalonMongoDB",
    "session_data_from_environment",

    "install",
    "uninstall",

    "schema",

    "Session",
    "session",

    "publish",

    "data",

    "register_host",
    "register_root",

    "registered_root",
    "registered_host",
    "registered_config",
]
