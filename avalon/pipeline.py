"""Core pipeline functionality"""

import sys
import logging


self = sys.modules[__name__]
self.data = {}
# The currently registered plugins from the last `discover` call.

log = logging.getLogger(__name__)


def publish():
    """Shorthand to publish from within host"""
    from pyblish import util
    return util.publish()
