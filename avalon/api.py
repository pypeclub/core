"""Public application programming interface

The following members are public and reliable.
That is to say, anything **not** defined here is **internal**
and likely **unreliable** for use outside of the codebase itself.

|
|

"""

from . import schema

from .lib import (
    time,
    logger,
    format_template_with_optional_keys
)

from .avalon_mongodb import (
    extract_port_from_url,
    requires_install,
    auto_reconnect,
    AvalonMongoConnection
)

from .pipeline import (
    install,
    uninstall,

    Loader,
    Creator,
    Action,
    InventoryAction,
    Application,
    discover,

    on,
    after,
    before,
    emit,

    publish,
    create,
    load,
    update,
    switch,
    remove,

    update_current_task,
    get_representation_path,
    loaders_from_representation,

    register_root,
    register_host,
    register_plugin_path,
    register_plugin,

    registered_host,
    registered_config,
    registered_plugin_paths,
    registered_root,

    deregister_plugin,
    deregister_plugin_path,

    HOST_WORKFILE_EXTENSIONS,
    should_start_last_workfile,
    last_workfile_with_version,
    last_workfile
)

from . import (
    Session,

    # Deprecated
    Session as session,
    data
)

__all__ = [
    # lib
    "format_template_with_optional_keys",
    "logger",
    "time",

    # avalon_mongodb
    "extract_port_from_url",
    "requires_install",
    "auto_reconnect",
    "AvalonMongoConnection",

    # pipeline
    "install",
    "uninstall",

    "schema",

    "Loader",
    "Creator",
    "Action",
    "InventoryAction",
    "Application",
    "discover",

    "on",
    "after",
    "before",
    "emit",

    "publish",
    "create",
    "load",
    "update",
    "switch",
    "remove",

    "update_current_task",
    "get_representation_path",
    "loaders_from_representation",

    "register_host",
    "register_plugin_path",
    "register_plugin",
    "register_root",

    "registered_root",
    "registered_plugin_paths",
    "registered_host",
    "registered_config",

    "deregister_plugin",
    "deregister_plugin_path",

    "HOST_WORKFILE_EXTENSIONS",
    "last_workfile_with_version",
    "last_workfile",

    "data",
    "Session",
    "session"
]
