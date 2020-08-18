"""This module holds state.

Modules in this package may modify state.

Erasing the contents of each container below will completely zero out
the currently held state of avalon-core.

"""



from .lib import session_data_from_environment
Session = session_data_from_environment(
    context_keys=True, global_keys=True
)
data = {}

from .host_context import HostContext
GLOBAL_CONTEXT = HostContext(session=Session, data=data)
