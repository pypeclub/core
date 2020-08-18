"""Core pipeline functionality"""

import os
import sys
import re
import json
import errno
import types
import copy
import shutil
import getpass
import logging
import weakref
import inspect
import traceback
import functools
import platform

from collections import OrderedDict

from . import io, lib, Session

from .vendor import six, acre
from pypeapp import Anatomy


log = logging.getLogger(__name__)

GLOBAL_CONTEXT = None
AVALON_CONTAINER_ID = "pyblish.avalon.container"

HOST_WORKFILE_EXTENSIONS = {
    "blender": [".blend"],
    "fusion": [".comp"],
    "harmony": [".zip"],
    "houdini": [".hip", ".hiplc", ".hipnc"],
    "maya": [".ma", ".mb"],
    "nuke": [".nk"],
    "nukestudio": [".hrox"],
    "photoshop": [".psd"],
    "premiere": [".prproj"],
    "resolve": [".drp"]
}
_registered_event_handlers = {}


class IncompatibleLoaderError(ValueError):
    """Error when Loader is incompatible with a representation."""
    pass


def publish():
    """Shorthand to publish from within host"""
    from pyblish import util
    return util.publish()


@lib.log
class Loader(list):
    """Load representation into host application

    Arguments:
        context (dict): avalon-core:context-1.0
        name (str, optional): Use pre-defined name
        namespace (str, optional): Use pre-defined namespace

    .. versionadded:: 4.0
       This class was introduced

    """

    families = list()
    representations = list()
    order = 0

    def __init__(self, context):
        representation = context['representation']
        project_doc = context.get("project")
        root = None
        if project_doc and project_doc["name"] != Session["AVALON_PROJECT"]:
            anatomy = Anatomy(project_doc["name"])
            root = anatomy.roots_obj

        self.fname = get_representation_path(representation, root)

    def load(self, context, name=None, namespace=None, options=None):
        """Load asset via database

        Arguments:
            context (dict): Full parenthood of representation to load
            name (str, optional): Use pre-defined name
            namespace (str, optional): Use pre-defined namespace
            options (dict, optional): Additional settings dictionary

        """
        raise NotImplementedError("Loader.load() must be "
                                  "implemented by subclass")

    def update(self, container, representation):
        """Update `container` to `representation`

        Arguments:
            container (avalon-core:container-1.0): Container to update,
                from `host.ls()`.
            representation (dict): Update the container to this representation.

        """
        raise NotImplementedError("Loader.update() must be "
                                  "implemented by subclass")

    def remove(self, container):
        """Remove a container

        Arguments:
            container (avalon-core:container-1.0): Container to remove,
                from `host.ls()`.

        Returns:
            bool: Whether the container was deleted

        """

        raise NotImplementedError("Loader.remove() must be "
                                  "implemented by subclass")


@lib.log
class Creator(object):
    """Determine how assets are created"""
    label = None
    family = None
    defaults = None

    def __init__(self, name, asset, options=None, data=None):
        self.name = name  # For backwards compatibility
        self.options = options

        # Default data
        self.data = OrderedDict()
        self.data["id"] = "pyblish.avalon.instance"
        self.data["family"] = self.family
        self.data["asset"] = asset
        self.data["subset"] = name
        self.data["active"] = True

        self.data.update(data or {})

    def process(self):
        pass


@lib.log
class Action(object):
    """A custom action available"""
    name = None
    label = None
    icon = None
    color = None
    order = 0

    def is_compatible(self, session):
        """Return whether the class is compatible with the Session."""
        return True

    def process(self, session, **kwargs):
        pass


class InventoryAction(object):
    """A custom action for the scene inventory tool

    If registered the action will be visible in the Right Mouse Button menu
    under the submenu "Actions".

    """

    label = None
    icon = None
    color = None
    order = 0

    @staticmethod
    def is_compatible(container):
        """Override function in a custom class

        This method is specifically used to ensure the action can operate on
        the container.

        Args:
            container(dict): the data of a loaded asset, see host.ls()

        Returns:
            bool
        """
        return bool(container.get("objectName"))

    def process(self, containers):
        """Override function in a custom class

        This method will receive all containers even those which are
        incompatible. It is advised to create a small filter along the lines
        of this example:

        valid_containers = filter(self.is_compatible(c) for c in containers)

        The return value will need to be a True-ish value to trigger
        the data_changed signal in order to refresh the view.

        You can return a list of container names to trigger GUI to select
        treeview items.

        You can return a dict to carry extra GUI options. For example:
            {
                "objectNames": [container names...],
                "options": {"mode": "toggle",
                            "clear": False}
            }
        Currently workable GUI options are:
            - clear (bool): Clear current selection before selecting by action.
                            Default `True`.
            - mode (str): selection mode, use one of these:
                          "select", "deselect", "toggle". Default is "select".

        Args:
            containers (list): list of dictionaries

        Return:
            bool, list or dict

        """
        return True


def compile_list_of_regexes(in_list):
    """Convert strings in entered list to compiled regex objects."""
    regexes = list()
    if not in_list:
        return regexes

    for item in in_list:
        if item:
            try:
                regexes.append(re.compile(item))
            except TypeError:
                log.warning((
                    "Invalid type \"{}\" value \"{}\"."
                    " Expected string based object. Skipping."
                ).format(str(type(item)), str(item)))
    return regexes


def should_start_last_workfile(project_name, host_name, task_name):
    """Define if host should start last version workfile if possible.

    Default output is `False`. Can be overriden with environment variable
    `AVALON_OPEN_LAST_WORKFILE`, valid values without case sensitivity are
    `"0", "1", "true", "false", "yes", "no"`.

    Args:
        project_name (str): Name of project.
        host_name (str): Name of host which is launched. In avalon's
            application context it's value stored in app definition under
            key `"application_dir"`. Is not case sensitive.
        task_name (str): Name of task which is used for launching the host.
            Task name is not case sensitive.

    Returns:
        bool: True if host should start workfile.

    """
    default_output = False

    env_override = os.environ.get("AVALON_OPEN_LAST_WORKFILE")
    if env_override is not None:
        env_override = env_override.lower().strip()
        if env_override in ("true", "yes", "1"):
            default_output = True
        elif env_override in ("false", "no", "0"):
            default_output = False

    try:
        from pype.api import config
        startup_presets = (
            config.get_presets(project_name)
            .get("tools", {})
            .get("workfiles", {})
            .get("last_workfile_on_startup")
        )
    except Exception:
        startup_presets = None
        log.warning("Couldn't load pype's presets", exc_info=True)

    if not startup_presets:
        return default_output

    host_name_lowered = host_name.lower()
    task_name_lowered = task_name.lower()

    max_points = 2
    matching_points = -1
    matching_item = None
    for item in startup_presets:
        hosts = item.get("hosts") or tuple()
        tasks = item.get("tasks") or tuple()

        hosts_lowered = tuple(_host_name.lower() for _host_name in hosts)
        # Skip item if has set hosts and current host is not in
        if hosts_lowered and host_name_lowered not in hosts_lowered:
            continue

        tasks_lowered = tuple(_task_name.lower() for _task_name in tasks)
        # Skip item if has set tasks and current task is not in
        if tasks_lowered:
            task_match = False
            for task_regex in compile_list_of_regexes(tasks_lowered):
                if re.match(task_regex, task_name_lowered):
                    task_match = True
                    break

            if not task_match:
                continue

        points = int(bool(hosts_lowered)) + int(bool(tasks_lowered))
        if points > matching_points:
            matching_item = item
            matching_points = points

        if matching_points == max_points:
            break

    if matching_item is not None:
        output = matching_item.get("enabled")
        if output is None:
            output = default_output
        return output
    return default_output


class Application(Action):
    """Default application launcher

    This is a convenience application Action that when "config" refers to a
    parsed application `.toml` this can launch the application.

    """

    config = None

    def is_compatible(self, session):
        required = ["AVALON_PROJECT",
                    "AVALON_ASSET",
                    "AVALON_TASK"]
        missing = [x for x in required if x not in session]
        if missing:
            self.log.debug("Missing keys: %s" % (missing,))
            return False
        return True

    def environ(self, session):
        """Build application environment"""

        session = session.copy()
        host_name = self.config["application_dir"]
        session["AVALON_APP"] = host_name
        session["AVALON_APP_NAME"] = self.name

        # Compute work directory
        project = io.find_one({"type": "project"})
        anatomy = Anatomy(project["name"])
        template_data = template_data_from_session(session)
        anatomy_filled = anatomy.format(template_data)
        session["AVALON_WORKDIR"] = anatomy_filled["work"]["folder"]

        last_workfile_path = None
        extensions = HOST_WORKFILE_EXTENSIONS.get(session["AVALON_APP"])
        if extensions:
            # Find last workfile
            file_template = anatomy.templates["work"]["file"]
            template_data.update({
                "version": 1,
                "user": getpass.getuser(),
                "ext": extensions[0]
            })

            last_workfile_path = last_workfile(
                session["AVALON_WORKDIR"],
                file_template,
                template_data,
                extensions,
                True
            )

        start_last_workfile = should_start_last_workfile(
            project["name"], host_name, session["AVALON_TASK"]
        )
        # Store boolean as "0"(False) or "1"(True)
        session["AVALON_OPEN_LAST_WORKFILE"] = (
            str(int(bool(start_last_workfile)))
        )

        if (
            start_last_workfile
            and last_workfile_path
            and os.path.exists(last_workfile_path)
        ):
            session["AVALON_LAST_WORKFILE"] = last_workfile_path

        # dynamic environmnets
        tools_attr = []
        if session["AVALON_APP"] is not None:
            tools_attr.append(session["AVALON_APP"])
        if session["AVALON_APP_NAME"] is not None:
            tools_attr.append(session["AVALON_APP_NAME"])

        # collect all the 'environment' attributes from parents
        asset = io.find_one({
            "type": "asset",
            "name": session["AVALON_ASSET"]
        })
        tools = self.find_tools(asset)
        tools_attr.extend(tools)

        tools_env = acre.get_tools(tools_attr)
        dyn_env = acre.compute(tools_env)
        env = acre.merge(dyn_env, current_env=dict(os.environ))

        # Build environment
        env.update(self.config.get("environment", {}))
        env.update(anatomy.root_environments())
        env.update(session)

        return env

    def find_tools(self, entity):
        tools = []
        if (
            'data' in entity
            and 'tools_env' in entity['data']
            and len(entity['data']['tools_env']) > 0
        ):
            tools = entity['data']['tools_env']

        elif (
            'data' in entity
            and 'visualParent' in entity['data']
            and entity['data']['visualParent'] is not None
        ):
            tmp = io.find_one({
                "_id": entity['data']['visualParent']
            })
            tools = self.find_tools(tmp)

        project = io.find_one({"_id": entity['parent']})

        if (
            'data' in project
            and 'tools_env' in project['data']
            and len(project['data']['tools_env']) > 0
        ):
            tools = project['data']['tools_env']

        return tools

    def initialize(self, environment):
        """Initialize work directory"""
        # Create working directory
        workdir = environment["AVALON_WORKDIR"]
        workdir_existed = os.path.exists(workdir)
        if not workdir_existed:
            os.makedirs(workdir)
            self.log.info("Creating working directory '%s'" % workdir)

            # Create default directories from app configuration
            default_dirs = self.config.get("default_dirs", [])
            default_dirs = self._format(default_dirs, **environment)
            if default_dirs:
                self.log.debug("Creating default directories..")
                for dirname in default_dirs:
                    try:
                        os.makedirs(os.path.join(workdir, dirname))
                        self.log.debug(" - %s" % dirname)
                    except OSError as e:
                        # An already existing default directory is fine.
                        if e.errno == errno.EEXIST:
                            pass
                        else:
                            raise

        # Perform application copy
        for src, dst in self.config.get("copy", {}).items():
            dst = os.path.join(workdir, dst)
            # Expand env vars
            src, dst = self._format([src, dst], **environment)

            try:
                self.log.info("Copying %s -> %s" % (src, dst))
                shutil.copy(src, dst)
            except OSError as e:
                self.log.error("Could not copy application file: %s" % e)
                self.log.error(" - %s -> %s" % (src, dst))

    def launch(self, environment):
        executable_path = self.config["executable"]
        pype_config_path = os.environ.get("PYPE_CONFIG")
        if pype_config_path:
            # Get platform folder name
            os_plat = platform.system().lower()
            # Path to folder with launchers
            path = os.path.join(pype_config_path, "launchers", os_plat)
            if os.path.exists(path):
                executable_path = os.path.join(path, executable_path)
        executable = lib.which(executable_path)

        if executable is None:
            raise ValueError(
                "'%s' not found on your PATH\n%s"
                % (self.config["executable"], os.getenv("PATH"))
            )

        args = self.config.get("args", [])
        return lib.launch(
            executable=executable,
            args=args,
            environment=environment,
            cwd=environment["AVALON_WORKDIR"]
        )

    def process(self, session, **kwargs):
        """Process the full Application action"""

        environment = self.environ(session)

        if kwargs.get("initialize", True):
            self.initialize(environment)

        if kwargs.get("launch", True):
            return self.launch(environment)

    def _format(self, original, **kwargs):
        """Utility recursive dict formatting that logs the error clearly."""

        try:
            return lib.dict_format(original, **kwargs)
        except KeyError as e:
            log.error(
                "One of the {variables} defined in the application "
                "definition wasn't found in this session.\n"
                "The variable was %s " % e
            )
            log.error(json.dumps(kwargs, indent=4, sort_keys=True))

            raise ValueError(
                "This is typically a bug in the pipeline, "
                "ask your developer.")


@lib.log
class ThumbnailResolver(object):
    """Determine how to get data from thumbnail entity.

    "priority" - determines the order of processing in `get_thumbnail_binary`,
        lower number is processed earlier.
    "thumbnail_types" - it is expected that thumbnails will be used in more
        more than one level, there is only ["thumbnail"] type at the moment
        of creating this docstring but it is expected to add "ico" and "full"
        in future.
    """

    priority = 100
    thumbnail_types = ["*"]

    def __init__(self, dbcon):
        self.dbcon = dbcon

    def process(self, thumbnail_entity, thumbnail_type):
        pass


class TemplateResolver(ThumbnailResolver):

    priority = 90

    def process(self, thumbnail_entity, thumbnail_type):

        if not os.environ.get("AVALON_THUMBNAIL_ROOT"):
            return

        template = thumbnail_entity["data"].get("template")
        if not template:
            log.debug("Thumbnail entity does not have set template")
            return

        project = self.dbcon.find_one({"type": "project"})

        template_data = copy.deepcopy(
            thumbnail_entity["data"].get("template_data") or {}
        )
        template_data.update({
            "_id": str(thumbnail_entity["_id"]),
            "thumbnail_type": thumbnail_type,
            "thumbnail_root": os.environ.get("AVALON_THUMBNAIL_ROOT"),
            "project": {
                "name": project["name"],
                "code": project["data"].get("code")
            }
        })

        try:
            filepath = os.path.normpath(template.format(**template_data))
        except KeyError:
            log.warning((
                "Missing template data keys for template <{0}> || Data: {1}"
            ).format(template, str(template_data)))
            return

        if not os.path.exists(filepath):
            log.warning("File does not exist \"{0}\"".format(filepath))
            return

        with open(filepath, "rb") as _file:
            content = _file.read()

        return content


class BinaryThumbnail(ThumbnailResolver):

    def process(self, thumbnail_entity, thumbnail_type):
        return thumbnail_entity["data"].get("binary_data")


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


def on(event, callback):
    """Call `callback` on `event`

    Register `callback` to be run when `event` occurs.

    Example:
        >>> def on_init():
        ...    print("Init happened")
        ...
        >>> on("init", on_init)
        >>> del on_init

    Arguments:
        event (str): Name of event
        callback (callable): Any callable

    """

    if event not in _registered_event_handlers:
        _registered_event_handlers[event] = weakref.WeakSet()

    events = _registered_event_handlers[event]
    events.add(callback)


def before(event, callback):
    """Convenience to `on()` for before-events"""
    on("before_" + event, callback)


def after(event, callback):
    """Convenience to `on()` for after-events"""
    on("after_" + event, callback)


def emit(event, args=None):
    """Trigger an `event`

    Example:
        >>> def on_init():
        ...    print("Init happened")
        ...
        >>> on("init", on_init)
        >>> emit("init")
        Init happened
        >>> del on_init

    Arguments:
        event (str): Name of event
        args (list, optional): List of arguments passed to callback

    """

    callbacks = _registered_event_handlers.get(event, set())
    args = args or list()

    for callback in callbacks:
        try:
            callback(*args)
        except Exception:
            log.warning(traceback.format_exc())


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
                "schema": "avalon-core:container-1.0",
                "name": "Bruce01",
                "objectName": "Bruce01_node",
                "namespace": "_bruce01_",
                "version": 3,
            },
            {
                "representation": "aa-bc-s-uuid2",
                "schema": "avalon-core:container-1.0",
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


def get_representation_context(representation, dbcon):
    """Return parenthood context for representation.

    Args:
        representation (str or io.ObjectId or dict): The representation id
            or full representation as returned by the database.

    Returns:
        dict: The full representation context.

    """

    assert representation is not None, "This is a bug"

    if isinstance(representation, (six.string_types, io.ObjectId)):
        representation = dbcon.find_one({
            "_id": dbcon.ObjectId(str(representation))
        })

    version, subset, asset, project = dbcon.parenthood(representation)

    assert all([representation, version, subset, asset, project]), (
        "This is a bug"
    )

    context = {
        "project": {
            "name": project["name"],
            "code": project["data"].get("code", '')
        },
        "asset": asset,
        "subset": subset,
        "version": version,
        "representation": representation,
    }

    return context


# TODO add dbcon argument or add function to host
def template_data_from_session(session):
    """ Return dictionary with template from session keys.

    Args:
        session (dict, Optional): The Session to use. If not provided use the
            currently active global Session.
    Returns:
        dict: All available data from session.
    """
    if session is None:
        session = Session

    project_name = session["AVALON_PROJECT"]
    project = io.database()[project_name].find_one({
        "type": "project"
    })

    return {
        "root": registered_root(),
        "project": {
            "name": project.get("name", session["AVALON_PROJECT"]),
            "code": project["data"].get("code", ""),
        },
        "asset": session["AVALON_ASSET"],
        "task": session["AVALON_TASK"],
        "app": session["AVALON_APP"],

        # Optional
        "silo": session.get("AVALON_SILO"),
        "user": session.get("AVALON_USER", getpass.getuser()),
        "hierarchy": session.get("AVALON_HIERARCHY"),
    }


# TODO add dbcon argument or add function to host
def compute_session_changes(session, task=None, asset=None, app=None):
    """Compute the changes for a Session object on asset, task or app switch

    This does *NOT* update the Session object, but returns the changes
    required for a valid update of the Session.

    Args:
        session (dict): The initial session to compute changes to.
            This is required for computing the full Work Directory, as that
            also depends on the values that haven't changed.
        task (str, Optional): Name of task to switch to.
        asset (str or dict, Optional): Name of asset to switch to.
            You can also directly provide the Asset dictionary as returned
            from the database to avoid an additional query. (optimization)
        app (str, Optional): Name of app to switch to.

    Returns:
        dict: The required changes in the Session dictionary.

    """

    changes = dict()

    # If no changes, return directly
    if not any([task, asset, app]):
        return changes

    # Get asset document and asset
    asset_document = None
    if asset:
        if isinstance(asset, dict):
            # Assume asset database document
            asset_document = asset
            asset = asset["name"]
        else:
            # Assume asset name
            asset_document = io.find_one({
                "name": asset,
                "type": "asset"
            })
            assert asset_document, "Asset must exist"

    # Detect any changes compared session
    mapping = {
        "AVALON_ASSET": asset,
        "AVALON_TASK": task,
        "AVALON_APP": app,
    }
    changes = {
        key: value
        for key, value in mapping.items()
        if value and value != session.get(key)
    }
    if not changes:
        return changes

    # Update silo and hierarchy when asset changed
    if "AVALON_ASSET" in changes:

        # Update silo
        changes["AVALON_SILO"] = asset_document.get("silo") or ""

        # Update hierarchy
        parents = asset_document['data'].get('parents', [])
        hierarchy = ""
        if len(parents) > 0:
            hierarchy = os.path.sep.join(parents)
        changes['AVALON_HIERARCHY'] = hierarchy

    # Compute work directory (with the temporary changed session so far)
    project = io.find_one({"type": "project"})
    _session = session.copy()
    _session.update(changes)
    anatomy = Anatomy(project["name"])
    template_data = template_data_from_session(_session)
    anatomy_filled = anatomy.format(template_data)
    changes["AVALON_WORKDIR"] = anatomy_filled["work"]["folder"]

    return changes


# TODO add dbcon argument or add function to host
def update_current_task(task=None, asset=None, app=None):
    """Update active Session to a new task work area.

    This updates the live Session to a different `asset`, `task` or `app`.

    Args:
        task (str): The task to set.
        asset (str): The asset to set.
        app (str): The app to set.

    Returns:
        dict: The changed key, values in the current Session.

    """

    changes = compute_session_changes(
        Session, task=task, asset=asset, app=app
    )

    # TODO do not set environments
    # Update the Session and environments. Pop from environments all keys with
    # value set to None.
    for key, value in changes.items():
        Session[key] = value
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    # TODO do this on host context level or on global level
    # Emit session change
    emit("taskChanged", changes.copy())

    return changes


def make_backwards_compatible_loader(Loader):
    """Convert a old-style Loaders with `process` method to new-style Loader

    This will make a dynamic class inheriting the old-style loader together
    with a BackwardsCompatibleLoader. This backwards compatible loader will
    expose `load`, `remove` and `update` in the same old way for Maya loaders.

    The `load` method will then call `process()` just like before.

    """

    # Assume new-style loader when no `process` method is exposed
    # then we don't swap the loader with a backwards compatible one.
    if not hasattr(Loader, "process"):
        return Loader

    log.warning("Making loader backwards compatible: %s", Loader.__name__)
    from avalon.maya.compat import BackwardsCompatibleLoader
    return type(Loader.__name__, (BackwardsCompatibleLoader, Loader), {})


def get_representation_path(representation, root=None, dbcon=None):
    """Get filename from representation document

    There are three ways of getting the path from representation which are
    tried in following sequence until successful.
    1. Get template from representation['data']['template'] and data from
       representation['context']. Then format template with the data.
    2. Get template from project['config'] and format it with default data set
    3. Get representation['data']['path'] and use it directly

    Args:
        representation(dict): representation document from the database

    Returns:
        str: fullpath of the representation

    """
    if dbcon is None:
        dbcon = io

    if root is None:
        root = registered_root()

    def path_from_represenation():
        try:
            template = representation["data"]["template"]
        except KeyError:
            return None

        try:
            context = representation["context"]
            context["root"] = root
            path = lib.format_template_with_optional_keys(context, template)
        except KeyError:
            # Template references unavailable data
            return None

        if not path:
            return path

        normalized_path = os.path.normpath(path)
        if os.path.exists(normalized_path):
            return normalized_path
        return path

    def path_from_config():
        try:
            version_, subset, asset, project = dbcon.parenthood(representation)
        except ValueError:
            log.debug(
                "Representation %s wasn't found in database, "
                "like a bug" % representation["name"]
            )
            return None

        try:
            template = project["config"]["template"]["publish"]
        except KeyError:
            log.debug(
                "No template in project %s, "
                "likely a bug" % project["name"]
            )
            return None

        # hierarchy may be equal to "" so it is not possible to use `or`
        hierarchy = asset.get("data", {}).get("hierarchy")
        if hierarchy is None:
            # default list() in get would not discover missing parents on asset
            parents = asset.get("data", {}).get("parents")
            if parents is not None:
                hierarchy = "/".join(parents)

        # Cannot fail, required members only
        data = {
            "root": root,
            "project": {
                "name": project["name"],
                "code": project.get("data", {}).get("code")
            },
            "asset": asset["name"],
            "silo": asset.get("silo"),
            "hierarchy": hierarchy,
            "subset": subset["name"],
            "version": version_["name"],
            "representation": representation["name"],
            "family": representation.get("context", {}).get("family"),
            "user": dbcon.Session.get("AVALON_USER", getpass.getuser()),
            "app": dbcon.Session.get("AVALON_APP", ""),
            "task": dbcon.Session.get("AVALON_TASK", "")
        }

        try:
            path = lib.format_template_with_optional_keys(data, template)
        except KeyError as e:
            log.debug("Template references unavailable data: %s" % e)
            return None

        normalized_path = os.path.normpath(path)
        if os.path.exists(normalized_path):
            return normalized_path
        return path

    def path_from_data():
        if "path" not in representation["data"]:
            return None

        path = representation["data"]["path"]
        if os.path.exists(path):
            return os.path.normpath(path)

        dir_path, file_name = os.path.split(path)
        if not os.path.exists(dir_path):
            return

        base_name, ext = os.path.splitext(file_name)
        file_name_items = None
        if "#" in base_name:
            file_name_items = [part for part in base_name.split("#") if part]
        elif "%" in base_name:
            file_name_items = base_name.split("%")

        if not file_name_items:
            return

        filename_start = file_name_items[0]

        for _file in os.listdir(dir_path):
            if _file.startswith(filename_start) and _file.endswith(ext):
                return os.path.normpath(path)

    return (
        path_from_represenation() or
        path_from_config() or
        path_from_data()
    )


def get_thumbnail_binary(thumbnail_entity, thumbnail_type, dbcon=None):
    if not thumbnail_entity:
        return

    resolvers = discover(ThumbnailResolver)
    if not resolvers:
        return resolvers

    resolvers = sorted(resolvers, key=lambda cls: cls.priority)
    if dbcon is None:
        dbcon = io

    for Resolver in resolvers:
        available_types = Resolver.thumbnail_types
        if (
            thumbnail_type not in available_types
            and "*" not in available_types
            and (
                isinstance(available_types, (list, tuple))
                and len(available_types) == 0
            )
        ):
            continue
        try:
            instance = Resolver(dbcon)
            result = instance.process(thumbnail_entity, thumbnail_type)
            if result:
                return result

        except Exception:
            log.warning("Resolver {0} failed durring process.".format(
                Resolver.__class__.__name__
            ))
            traceback.print_exception(*sys.exc_info())


def is_compatible_loader(Loader, context):
    """Return whether a loader is compatible with a context.

    This checks the version's families and the representation for the given
    Loader.

    Returns:
        bool

    """
    if context["subset"]["schema"] == "avalon-core:subset-3.0":
        families = context["subset"]["data"]["families"]
    else:
        families = context["version"]["data"].get("families", [])

    representation = context["representation"]
    has_family = ("*" in Loader.families or
                  any(family in Loader.families for family in families))
    has_representation = ("*" in Loader.representations or
                          representation["name"] in Loader.representations)
    return has_family and has_representation


def loaders_from_representation(loaders, representation, dbcon):
    """Return all compatible loaders for a representation."""

    context = get_representation_context(representation, dbcon)
    return [
        loader
        for loader in loaders
        if is_compatible_loader(loader, context)
    ]


def last_workfile_with_version(workdir, file_template, fill_data, extensions):
    """Return last workfile version.

    Args:
        workdir(str): Path to dir where workfiles are stored.
        file_template(str): Template of file name.
        fill_data(dict): Data for filling template.
        extensions(list, tuple): All allowed file extensions of workfile.

    Returns:
        tuple: Last workfile<str> with version<int> if there is any otherwise
            returns (None, None).
    """
    if not os.path.exists(workdir):
        return None, None

    # Fast match on extension
    filenames = [
        filename
        for filename in os.listdir(workdir)
        if os.path.splitext(filename)[1] in extensions
    ]

    # Build template without optionals, version to digits only regex
    # and comment to any definable value.
    file_template = re.sub("<.*?>", ".*?", file_template)
    file_template = re.sub("{version.*}", "([0-9]+)", file_template)
    file_template = re.sub("{comment.*?}", ".+?", file_template)
    partially_filled = lib.format_template_with_optional_keys(
        fill_data,
        file_template
    )

    _ext = []
    for ext in extensions:
        if not ext.startswith("."):
            ext = "." + ext
        # Escape dot for regex
        ext = "\\" + ext
        _ext.append(ext)

    # Add or regex expression for extensions
    partially_filled += "(?:" + "|".join(_ext) + ")"
    file_template = "^" + partially_filled + "$"

    # Match with ignore case on Windows due to the Windows
    # OS not being case-sensitive. This avoids later running
    # into the error that the file did exist if it existed
    # with a different upper/lower-case.
    kwargs = {}
    if platform.system().lower() == "windows":
        kwargs["flags"] = re.IGNORECASE

    # Get highest version among existing matching files
    output_filename = None
    version = None
    for filename in sorted(filenames):
        match = re.match(file_template, filename, **kwargs)
        if match:
            file_version = int(match.group(1))
            if version is None or file_version >= version:
                version = file_version
                output_filename = filename
    return output_filename, version


def last_workfile(
    workdir, file_template, fill_data, extensions, full_path=False
):
    """Return last workfile filename.

    Returns file with version 1 if there is not workfile yet.

    Args:
        workdir(str): Path to dir where workfiles are stored.
        file_template(str): Template of file name.
        fill_data(dict): Data for filling template.
        extensions(list, tuple): All allowed file extensions of workfile.
        full_path(bool): Full path to file is returned if set to True.

    Returns:
        str: Last or first workfile as filename of full path to filename.
    """
    filename, version = last_workfile_with_version(
        workdir, file_template, fill_data, extensions
    )
    if filename is None:
        data = copy.deepcopy(fill_data)
        data["version"] = 1
        data.pop("comment", None)
        if not data.get("ext"):
            data["ext"] = extensions[0]
        filename = lib.format_template_with_optional_keys(data, file_template)

    if full_path:
        return os.path.join(workdir, filename)
    return filename


def check_global_context(func):
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        global GLOBAL_CONTEXT
        if GLOBAL_CONTEXT is None:
            from . import GLOBAL_CONTEXT as _GLOBAL_CONTEXT
            GLOBAL_CONTEXT = _GLOBAL_CONTEXT
        return func(*args, **kwargs)
    return decorated


@check_global_context
def install(host):
    return GLOBAL_CONTEXT.install(host)


@check_global_context
def uninstall():
    return GLOBAL_CONTEXT.uninstall()


@check_global_context
def is_installed():
    return GLOBAL_CONTEXT.is_installed()


@check_global_context
def register_plugin(superclass, obj):
    return GLOBAL_CONTEXT.register_plugin(superclass, obj)


@check_global_context
def deregister_plugin(superclass, plugin):
    return GLOBAL_CONTEXT.deregister_plugin(superclass, plugin)


@check_global_context
def register_plugin_path(superclass, path):
    return GLOBAL_CONTEXT.register_plugin_path(superclass, path)


@check_global_context
def registered_plugin_paths():
    return GLOBAL_CONTEXT.registered_plugin_paths()


@check_global_context
def deregister_plugin_path(superclass, path):
    return GLOBAL_CONTEXT.deregister_plugin_path(superclass, path)


@check_global_context
def register_root(path):
    return GLOBAL_CONTEXT.register_root(path)


@check_global_context
def registered_root():
    return GLOBAL_CONTEXT.registered_root()


@check_global_context
def register_host(host):
    return GLOBAL_CONTEXT.register_host(host)


@check_global_context
def registered_host():
    return GLOBAL_CONTEXT.registered_host()


@check_global_context
def deregister_host():
    return GLOBAL_CONTEXT.deregister_host()


@check_global_context
def register_config(config):
    return GLOBAL_CONTEXT.register_config(config)


@check_global_context
def registered_config():
    return GLOBAL_CONTEXT.registered_config()


@check_global_context
def deregister_config():
    return GLOBAL_CONTEXT.deregister_config()


@check_global_context
def _get_container_loader(container):
    return GLOBAL_CONTEXT._get_container_loader(container)


@check_global_context
def discover(superclass):
    return GLOBAL_CONTEXT.discover(superclass)


@check_global_context
def create(name, asset, family, options=None, data=None):
    return GLOBAL_CONTEXT.create(name, asset, family, options=None, data=None)


@check_global_context
def load(
    Loader, representation,
    namespace=None, name=None, options=None, **kwargs
):
    return GLOBAL_CONTEXT.load(
        Loader, representation,
        namespace=None, name=None, options=None, **kwargs
    )


@check_global_context
def remove(container):
    return GLOBAL_CONTEXT.remove(container)


@check_global_context
def update(container, version=None):
    return GLOBAL_CONTEXT.update(container, version=None)


@check_global_context
def switch(container, representation):
    return GLOBAL_CONTEXT.switch(container, representation)
