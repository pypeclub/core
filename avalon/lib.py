"""Helper functions"""

import os
import sys
import logging
import importlib
import types
import numbers

import six

log = logging.getLogger(__name__)


def modules_from_path(path):
    """Get python scripts as modules from a path.

    Arguments:
        path (str): Path to folder containing python scripts.

    Returns:
        List of modules.
    """

    path = os.path.normpath(path)

    if not os.path.isdir(path):
        log.warning("%s is not a directory" % path)
        return []

    modules = []
    for fname in os.listdir(path):
        # Ignore files which start with underscore
        if fname.startswith("_"):
            continue

        mod_name, mod_ext = os.path.splitext(fname)
        if not mod_ext == ".py":
            continue

        abspath = os.path.join(path, fname)
        if not os.path.isfile(abspath):
            continue

        module = types.ModuleType(mod_name)
        module.__file__ = abspath

        try:
            with open(abspath) as f:
                six.exec_(f.read(), module.__dict__)

            # Store reference to original module, to avoid
            # garbage collection from collecting it's global
            # imports, such as `import os`.
            sys.modules[mod_name] = module

        except Exception as err:
            print("Skipped: \"{0}\" ({1})".format(mod_name, err))
            continue

        modules.append(module)

    return modules


def find_submodule(module, submodule):
    """Find and return submodule of the module.

    Args:
        module (types.ModuleType): The module to search in.
        submodule (str): The submodule name to find.

    Returns:
        types.ModuleType or None: The module, if found.

    """
    templates = (
        "{0}.hosts.{1}.api",
        "{0}.hosts.{1}",
        "{0}.{1}"
    )
    for template in templates:
        try:
            name = template.format(module.__name__, submodule)
            return importlib.import_module(name)
        except ImportError:
            log.warning(
                "Could not find \"{}\".".format(name),
                exc_info=True
            )

    log.warning(
        "Could not find '%s' in module: %s", submodule, module
    )
