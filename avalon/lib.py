"""Helper functions"""

import os
import sys
import json
import logging
import datetime
import importlib
import subprocess
import types
import numbers

from . import schema
from .vendor import six, toml

PY2 = sys.version_info[0] == 2

log_ = logging.getLogger(__name__)

# Backwards compatibility
logger = log_

__all__ = [
    "time",
    "log",
]


def time():
    """Return file-system safe string of current date and time"""
    return datetime.datetime.now().strftime("%Y%m%dT%H%M%SZ")


def log(cls):
    """Decorator for attaching a logger to the class `cls`

    Loggers inherit the syntax {module}.{submodule}

    Example
        >>> @log
        ... class MyClass(object):
        ...     pass
        >>>
        >>> myclass = MyClass()
        >>> myclass.log.info('Hello World')

    """

    module = cls.__module__
    name = cls.__name__

    # Package name appended, for filtering of LogRecord instances
    logname = "%s.%s" % (module, name)
    cls.log = logging.getLogger(logname)

    # All messages are handled by root-logger
    cls.log.propagate = True

    return cls


def dict_format(original, **kwargs):
    """Recursively format the values in *original* with *kwargs*.

    Example:
        >>> sample = {"key": "{value}", "sub-dict": {"sub-key": "sub-{value}"}}
        >>> dict_format(sample, value="Bob") == \
            {'key': 'Bob', 'sub-dict': {'sub-key': 'sub-Bob'}}
        True

    """

    new_dict = dict()
    new_list = list()

    if isinstance(original, dict):
        for key, value in original.items():
            if isinstance(value, dict):
                new_dict[key.format(**kwargs)] = dict_format(value, **kwargs)
            elif isinstance(value, list):
                new_dict[key.format(**kwargs)] = dict_format(value, **kwargs)
            elif isinstance(value, six.string_types):
                new_dict[key.format(**kwargs)] = value.format(**kwargs)
            else:
                new_dict[key.format(**kwargs)] = value

        return new_dict

    else:
        assert isinstance(original, list)
        for value in original:
            if isinstance(value, dict):
                new_list.append(dict_format(value, **kwargs))
            elif isinstance(value, list):
                new_list.append(dict_format(value, **kwargs))
            elif isinstance(value, six.string_types):
                new_list.append(value.format(**kwargs))
            else:
                new_list.append(value)

        return new_list


def which(program):
    """Locate `program` in PATH

    Arguments:
        program (str): Name of program, e.g. "python"

    """

    def is_exe(fpath):
        if os.path.isfile(fpath) and os.access(fpath, os.X_OK):
            return True
        return False

    for path in os.environ["PATH"].split(os.pathsep):
        for ext in os.getenv("PATHEXT", "").split(os.pathsep):
            fname = program + ext.lower()
            abspath = os.path.join(path.strip('"'), fname)

            if is_exe(abspath):
                return abspath

    return None


def which_app(app):
    """Locate `app` in PATH

    Arguments:
        app (str): Name of app, e.g. "python"

    """

    for path in os.environ["PATH"].split(os.pathsep):
        fname = app + ".toml"
        abspath = os.path.join(path.strip('"'), fname)

        if os.path.isfile(abspath):
            return abspath

    return None


def get_application(name):
    """Find the application .toml and parse it.

    Arguments:
        name (str): The name of the application to search.

    Returns:
        dict: The parsed application from the .toml settings.

    """
    application_definition = which_app(name)

    if application_definition is None:
        raise ValueError(
            "No application definition could be found for '%s'" % name
        )

    try:
        with open(application_definition) as f:
            app = toml.load(f)
            log_.debug(json.dumps(app, indent=4))
            schema.validate(app, "application")
    except (schema.ValidationError,
            schema.SchemaError,
            toml.TomlDecodeError) as e:
        log_.error("%s was invalid." % application_definition)
        raise

    return app


def launch(executable, args=None, environment=None, cwd=None):
    """Launch a new subprocess of `args`

    Arguments:
        executable (str): Relative or absolute path to executable
        args (list): Command passed to `subprocess.Popen`
        environment (dict, optional): Custom environment passed
            to Popen instance.

    Returns:
        Popen instance of newly spawned process

    Exceptions:
        OSError on internal error
        ValueError on `executable` not found

    """

    CREATE_NO_WINDOW = 0x08000000
    CREATE_NEW_CONSOLE = 0x00000010
    IS_WIN32 = sys.platform == "win32"
    PY2 = sys.version_info[0] == 2

    abspath = executable

    env = (environment or os.environ)

    if PY2:
        # Protect against unicode, and other unsupported
        # types amongst environment variables
        enc = sys.getfilesystemencoding()
        env = {k.encode(enc): v.encode(enc) for k, v in env.items()}

    kwargs = dict(
        args=[abspath] + args or list(),
        env=env,
        cwd=cwd,

        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,

        # Output `str` through stdout on Python 2 and 3
        universal_newlines=True,
    )

    # this won't do anything on linux/macos as `creationFlags` are
    # only windows specific.
    if IS_WIN32 and env.get("CREATE_NEW_CONSOLE"):
        kwargs["creationflags"] = CREATE_NEW_CONSOLE
        kwargs.pop("stdout")
        kwargs.pop("stderr")
    else:
        if IS_WIN32:
            kwargs["creationflags"] = CREATE_NO_WINDOW

    popen = subprocess.Popen(**kwargs)

    return popen


def modules_from_path(path):
    """Get python scripts as modules from a path.

    Arguments:
        path (str): Path to folder containing python scripts.

    Returns:
        List of modules.
    """

    path = os.path.normpath(path)

    if not os.path.isdir(path):
        log_.warning("%s is not a directory" % path)
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
    try:
        name = "{0}.hosts.{1}".format(module.__name__, submodule)
        return importlib.import_module(name)
    except ImportError:
        log_.warning(
            (
                "Could not find \"{}\". Trying backwards compatible approach."
            ).format(name),
            exc_info=True
        )
        try:
            name = "{0}.{1}".format(module.__name__, submodule)
            return importlib.import_module(name)
        except ImportError as exc:
            if str(exc) != "No module name {}".format(name):
                log_.warning(
                    "Could not find '%s' in module: %s", submodule, module
                )


class MasterVersionType(object):
    def __init__(self, version):
        assert isinstance(version, numbers.Integral), (
            "Version is not an integer. \"{}\" {}".format(
                version, str(type(version))
            )
        )
        self.version = version

    def __str__(self):
        return str(self.version)

    def __int__(self):
        return int(self.version)

    def __format__(self, format_spec):
        return self.version.__format__(format_spec)


SESSION_CONTEXT_KEYS = (
    # Root directory of projects on disk
    "AVALON_PROJECTS",
    # Name of current Project
    "AVALON_PROJECT",
    # Name of current Asset
    "AVALON_ASSET",
    # Name of current silo
    "AVALON_SILO",
    # Name of current task
    "AVALON_TASK",
    # Name of current app
    "AVALON_APP",
    # Path to working directory
    "AVALON_WORKDIR",
    # Optional path to scenes directory (see Work Files API)
    "AVALON_SCENEDIR",
    # Optional hierarchy for the current Asset. This can be referenced
    # as `{hierarchy}` in your file templates.
    # This will be (re-)computed when you switch the context to another
    # asset. It is computed by checking asset['data']['parents'] and
    # joining those together with `os.path.sep`.
    # E.g.: ['ep101', 'scn0010'] -> 'ep101/scn0010'.
    "AVALON_HIERARCHY"
)


def session_data_from_environment(*, global_keys=True, context_keys=False):
    session_data = {}
    if context_keys:
        for key in SESSION_CONTEXT_KEYS:
            value = os.environ.get(key)
            session_data[key] = value

    if not global_keys:
        return session_data

    for key, default_value in (
        # Name of current Config
        # TODO(marcus): Establish a suitable default config
        ("AVALON_CONFIG", "no_config"),

        # Name of Avalon in graphical user interfaces
        # Use this to customise the visual appearance of Avalon
        # to better integrate with your surrounding pipeline
        ("AVALON_LABEL", "Avalon"),

        # Used during any connections to the outside world
        ("AVALON_TIMEOUT", "1000"),

        # Address to Asset Database
        ("AVALON_MONGO", "mongodb://localhost:27017"),

        # Name of database used in MongoDB
        ("AVALON_DB", "avalon"),

        # Address to Sentry
        ("AVALON_SENTRY", None),

        # Address to Deadline Web Service
        # E.g. http://192.167.0.1:8082
        ("AVALON_DEADLINE", None),

        # Enable features not necessarily stable, at the user's own risk
        ("AVALON_EARLY_ADOPTER", None),

        # Address of central asset repository, contains
        # the following interface:
        #   /upload
        #   /download
        #   /manager (optional)
        ("AVALON_LOCATION", "http://127.0.0.1"),

        # Boolean of whether to upload published material
        # to central asset repository
        ("AVALON_UPLOAD", None),

        # Generic username and password
        ("AVALON_USERNAME", "avalon"),
        ("AVALON_PASSWORD", "secret"),

        # Unique identifier for instances in working files
        ("AVALON_INSTANCE_ID", "avalon.instance"),
        ("AVALON_CONTAINER_ID", "avalon.container"),

        # Enable debugging
        ("AVALON_DEBUG", None)
    ):
        value = os.environ.get(key) or default_value
        session_data[key] = value

    return session_data
