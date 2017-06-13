"""Public API

Anything that is not defined here is **internal** and
unreliable for external use.

Motivation for api.py:
    Storing the API in a module, as opposed to in __init__.py, enables
    use of it internally.

    For example, from `pipeline.py`:
        >> from . import api
        >> api.do_this()

    The important bit is avoiding circular dependencies, where api.py
    is calling upon a module which in turn calls upon api.py.

"""

import logging

from . import schema

from .pipeline import (
    install,
    uninstall,

    Loader,
    Creator,
    discover,

    register_root,
    register_data,
    register_host,
    register_format,
    register_silo,
    register_family,
    register_plugin_path,
    register_plugin,

    registered_host,
    registered_families,
    registered_plugin_paths,
    registered_formats,
    registered_data,
    registered_root,
    registered_silos,

    deregister_plugins,
    deregister_format,
    deregister_family,
    deregister_data,
)

from .lib import (
    format_staging_dir,
    format_shared_dir,
    format_version,

    time,

    find_latest_version,
    parse_version,
)

logging.basicConfig()
logger = logging.getLogger("mindbender")


__all__ = [
    "install",
    "uninstall",

    "schema",

    "Loader",
    "Creator",
    "discover",

    "register_host",
    "register_data",
    "register_format",
    "register_silo",
    "register_family",
    "register_plugin_path",
    "register_plugin",
    "register_root",

    "registered_root",
    "registered_silos",
    "registered_plugin_paths",
    "registered_host",
    "registered_families",
    "registered_formats",
    "registered_data",

    "deregister_plugins",
    "deregister_format",
    "deregister_family",
    "deregister_data",

    "format_staging_dir",
    "format_shared_dir",
    "format_version",

    "find_latest_version",
    "parse_version",

    "time",
]
