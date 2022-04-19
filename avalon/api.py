"""Public application programming interface

The following members are public and reliable.
That is to say, anything **not** defined here is **internal**
and likely **unreliable** for use outside of the codebase itself.

|
|

"""

from . import (
    schema,
    Session,
)
from . mongodb import (
    AvalonMongoDB,
    session_data_from_environment
)

session = Session


__all__ = [
    "schema",
    "Session",
    "session",

    "AvalonMongoDB",
    "session_data_from_environment",
]
