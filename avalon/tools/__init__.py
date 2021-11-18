import sys

# Backwards compatibility
from . import (
    sceneinventory as cbsceneinventory,
)

from .lib import (
    application,
)

# Support `import avalon.tools.cbloader`
sys.modules[__name__ + ".cbsceneinventory"] = cbsceneinventory

__all__ = [
    "application",

    "cbsceneinventory",
]
