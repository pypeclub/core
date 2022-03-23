"""Core pipeline functionality"""

import os
import sys
import json
import types
import logging
import inspect
import importlib

from . import (
    io,
    lib,

    Session,

    _registered_host,
    _registered_root,
    _registered_config,
)

self = sys.modules[__name__]
self._is_installed = False
self._config = None
self.data = {}
# The currently registered plugins from the last `discover` call.

log = logging.getLogger(__name__)


def install(host):
    """Install `host` into the running Python session.
    Arguments:
        host (module): A Python module containing the Avalon
            avalon host-interface.
    """

    io.install()

    missing = list()
    for key in ("AVALON_PROJECT", "AVALON_ASSET"):
        if key not in Session:
            missing.append(key)

    assert not missing, (
        "%s missing from environment, %s" % (
            ", ".join(missing),
            json.dumps(Session, indent=4, sort_keys=True)
        ))

    project = Session["AVALON_PROJECT"]
    log.info("Activating %s.." % project)

    config = find_config()

    # Optional host install function
    if hasattr(host, "install"):
        host.install()

    # Optional config.host.install()
    host_name_parts = host.__name__.split(".")
    host_name = host_name_parts[-1]
    # Go to second from end if last item name is named 'api'
    if host_name == "api":
        host_name = host_name_parts[-2]
    config_host = lib.find_submodule(config, host_name)
    if config_host != host:
        if hasattr(config_host, "install"):
            config_host.install()

    register_host(host)
    register_config(config)

    config.install()

    self._is_installed = True
    self._config = config
    log.info("Successfully installed Avalon!")


def find_config():
    log.info("Finding configuration for project..")

    config = Session["AVALON_CONFIG"]
    if not config:
        raise EnvironmentError("No configuration found in "
                               "the project nor environment")

    log.info("Found %s, loading.." % config)
    return importlib.import_module(config)


def uninstall():
    """Undo all of what `install()` did"""
    config = registered_config()
    host = registered_host()

    # Optional config.host.uninstall()
    host_name = host.__name__.rsplit(".", 1)[-1]
    config_host = lib.find_submodule(config, host_name)
    if hasattr(config_host, "uninstall"):
        config_host.uninstall()

    try:
        host.uninstall()
    except AttributeError:
        pass

    try:
        config.uninstall()
    except AttributeError:
        pass

    deregister_host()
    deregister_config()

    io.uninstall()

    log.info("Successfully uninstalled Avalon!")


def is_installed():
    """Return state of installation

    Returns:
        True if installed, False otherwise

    """

    return self._is_installed


def publish():
    """Shorthand to publish from within host"""
    from pyblish import util
    return util.publish()


def plugin_from_module(superclass, module):
    """Return plug-ins from module

    Arguments:
        superclass (superclass): Superclass of subclasses to look for
        module (types.ModuleType): Imported module from which to
            parse valid Avalon plug-ins.

    Returns:
        List of plug-ins, or empty list if none is found.

    """

    types = list()

    def recursive_bases(klass):
        r = []
        bases = klass.__bases__
        r.extend(bases)
        for base in bases:
            r.extend(recursive_bases(base))
        return r

    for name in dir(module):

        # It could be anything at this point
        obj = getattr(module, name)

        if not inspect.isclass(obj):
            continue

        # These are subclassed from nothing, not even `object`
        if not len(obj.__bases__) > 0:
            continue

        # Use string comparison rather than `issubclass`
        # in order to support reloading of this module.
        bases = recursive_bases(obj)
        if not any(base.__name__ == superclass.__name__ for base in bases):
            continue

        types.append(obj)

    return types


def register_root(path):
    """Register currently active root"""
    log.info("Registering root: %s" % path)
    _registered_root["_"] = path


def registered_root():
    """Return currently registered root"""
    root = _registered_root["_"]
    if root:
        return root

    root = Session.get("AVALON_PROJECTS")
    if root:
        return os.path.normpath(root)

    return ""


def register_host(host):
    """Register a new host for the current process

    Arguments:
        host (ModuleType): A module implementing the
            Host API interface. See the Host API
            documentation for details on what is
            required, or browse the source code.

    """
    signatures = {
        "ls": []
    }

    _validate_signature(host, signatures)
    _registered_host["_"] = host


def register_config(config):
    """Register a new config for the current process

    Arguments:
        config (ModuleType): A module implementing the Config API.

    """

    signatures = {
        "install": [],
        "uninstall": [],
    }

    _validate_signature(config, signatures)
    _registered_config["_"] = config


def _validate_signature(module, signatures):
    # Required signatures for each member

    missing = list()
    invalid = list()
    success = True

    for member in signatures:
        if not hasattr(module, member):
            missing.append(member)
            success = False

        else:
            attr = getattr(module, member)
            if sys.version_info.major >= 3:
                signature = inspect.getfullargspec(attr)[0]
            else:
                signature = inspect.getargspec(attr)[0]
            required_signature = signatures[member]

            assert isinstance(signature, list)
            assert isinstance(required_signature, list)

            if not all(member in signature
                       for member in required_signature):
                invalid.append({
                    "member": member,
                    "signature": ", ".join(signature),
                    "required": ", ".join(required_signature)
                })
                success = False

    if not success:
        report = list()

        if missing:
            report.append(
                "Incomplete interface for module: '%s'\n"
                "Missing: %s" % (module, ", ".join(
                    "'%s'" % member for member in missing))
            )

        if invalid:
            report.append(
                "'%s': One or more members were found, but didn't "
                "have the right argument signature." % module.__name__
            )

            for member in invalid:
                report.append(
                    "     Found: {member}({signature})".format(**member)
                )
                report.append(
                    "  Expected: {member}({required})".format(**member)
                )

        raise ValueError("\n".join(report))


def deregister_config():
    """Undo `register_config()`"""
    _registered_config["_"] = None


def registered_config():
    """Return currently registered config"""
    return _registered_config["_"]


def registered_host():
    """Return currently registered host"""
    return _registered_host["_"]


def deregister_host():
    _registered_host["_"] = default_host()


def default_host():
    """A default host, in place of anything better

    This may be considered as reference for the
    interface a host must implement. It also ensures
    that the system runs, even when nothing is there
    to support it.

    """

    host = types.ModuleType("defaultHost")

    def ls():
        return list()

    host.__dict__.update({
        "ls": ls
    })

    return host


def debug_host():
    """A debug host, useful to debugging features that depend on a host"""

    host = types.ModuleType("debugHost")

    def ls():
        containers = [
            {
                "representation": "ee-ft-a-uuid1",
                "schema": "openpype:container-1.0",
                "name": "Bruce01",
                "objectName": "Bruce01_node",
                "namespace": "_bruce01_",
                "version": 3,
            },
            {
                "representation": "aa-bc-s-uuid2",
                "schema": "openpype:container-1.0",
                "name": "Bruce02",
                "objectName": "Bruce01_node",
                "namespace": "_bruce02_",
                "version": 2,
            }
        ]

        for container in containers:
            yield container

    host.__dict__.update({
        "ls": ls,
        "open_file": lambda fname: None,
        "save_file": lambda fname: None,
        "current_file": lambda: os.path.expanduser("~/temp.txt"),
        "has_unsaved_changes": lambda: False,
        "work_root": lambda: os.path.expanduser("~/temp"),
        "file_extensions": lambda: ["txt"],
    })

    return host
