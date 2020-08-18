import os
import sys
import inspect
import importlib
import logging
from uuid import uuid4
from bson.objectid import ObjectId

from . import lib, schema, avalon_mongodb, api, pipeline


class HostContext:
    session_schema = "avalon-core:session-2.0"

    def __init__(
        self, session=None, data=None, context_keys_from_environ=False
    ):
        self._id = uuid4()
        self._is_installed = False

        self.log = logging.getLogger(self.__class__.__name__)
        self.data = data or {}

        self.config = None
        if session is None:
            session = lib.session_data_from_environment(
                context_keys=context_keys_from_environ
            )
        self.Session = session
        self.Session["schema"] = self.session_schema

        self.dbcon = avalon_mongodb.AvalonMongoConnection(self.Session)

        self._registered_host = None
        self._registered_root = None
        self._registered_plugins = {}
        self._registered_plugin_paths = {}

        self._sentry_client = None
        self._sentry_logging_handler = None

    def id(self):
        return self._id

    @property
    def is_installed(self):
        return self._is_installed

    def find_config(self):
        self.log.info("Finding configuration for project..")

        config = self.Session["AVALON_CONFIG"]
        if not config:
            raise EnvironmentError(
                "No configuration found in the project nor environment"
            )

        self.log.info("Found config: \"{}\", loading..".format(config))
        return importlib.import_module(config)

    def install(self, host, context_keys=None):
        """Install `host` into the running Python session.
        Arguments:
            host (module): A Python module containing the Avalon
                avalon host-interface.
        """
        schema.validate(self.Session)

        self.dbcon.install()

        missing = list()
        for key in ("AVALON_PROJECT", "AVALON_ASSET"):
            if key not in self.Session:
                missing.append(key)

        self.log.warning(
            "Missing session keys on install: {}".format(", ".join(missing))
        )

        project_name = self.Session.get("AVALON_PROJECT")
        if project_name:
            self.log.info("Active project: {}".format(project_name))

        config = self.find_config()

        # Optional host install function
        if hasattr(host, "install"):
            host.install()

        # Optional config.host.install()
        host_name = host.__name__.rsplit(".", 1)[-1]
        config_host = lib.find_submodule(config, host_name)
        if config_host != host and hasattr(config_host, "install"):
            config_host.install()

        self.register_host(host)
        self.register_config(config)
        self.register_default_plugins()

        config.install()

        self._is_installed = True
        self._config = config
        self.log.info("Successfully installed Avalon!")

    def uninstall(self):
        """Undo all of what `install()` did"""
        config = self.registered_config()
        host = self.registered_host()

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

        self.deregister_host()
        self.deregister_config()

        self.dbcon.uninstall()

        self.log.info("Successfully uninstalled Avalon!")

    def discover(self, superclass):
        """Find and return subclasses of `superclass`"""

        registered = self._registered_plugins.get(superclass, list())
        plugins = dict()

        # Include plug-ins from registered paths
        for path in self._registered_plugin_paths.get(superclass, list()):
            for module in lib.modules_from_path(path):
                for plugin in pipeline.plugin_from_module(superclass, module):
                    if plugin.__name__ in plugins:
                        print("Duplicate plug-in found: %s" % plugin)
                        continue

                    plugins[plugin.__name__] = plugin

        for plugin in registered:
            if plugin.__name__ in plugins:
                print("Warning: Overwriting %s" % plugin.__name__)
            plugins[plugin.__name__] = plugin

        return sorted(plugins.values(), key=lambda Plugin: Plugin.__name__)

    def register_default_plugins(self):
        # TODO add them to global plugins
        self.register_plugin(api.ThumbnailResolver, api.BinaryThumbnail)
        self.register_plugin(api.ThumbnailResolver, api.TemplateResolver)

    def register_plugin_path(self, superclass, path):
        """Register a directory of one or more plug-ins

        Arguments:
            superclass (type): Superclass of plug-ins to look for
                during discovery
            path (str): Absolute path to directory in which to
                discover plug-ins
        """

        if superclass not in self._registered_plugin_paths:
            self._registered_plugin_paths[superclass] = list()

        path = os.path.normpath(path)
        if path not in self._registered_plugin_paths[superclass]:
            self._registered_plugin_paths[superclass].append(path)

    def registered_plugin_paths(self):
        """Return all currently registered plug-in paths"""

        # Prohibit editing in-place
        duplicate = {
            superclass: paths[:]
            for superclass, paths in self._registered_plugin_paths.items()
        }

        return duplicate

    def deregister_plugin_path(self, superclass, path):
        """Oppsite of `register_plugin_path()`"""
        self._registered_plugin_paths[superclass].remove(path)

    def register_plugin(self, superclass, obj):
        """Register an individual `obj` of type `superclass`

        Arguments:
            superclass (type): Superclass of plug-in
            obj (object): Subclass of `superclass`

        """

        if superclass not in self._registered_plugins:
            self._registered_plugins[superclass] = list()

        if obj not in self._registered_plugins[superclass]:
            self._registered_plugins[superclass].append(obj)

    def deregister_plugin(self, superclass, plugin):
        """Oppsite of `register_plugin()`"""
        self._registered_plugins[superclass].remove(plugin)

    def register_root(self, roots):
        """Register currently active root"""
        self.log.info("Registering root: {}".format(roots))
        self._registered_root = roots

    def registered_root(self):
        """Return currently registered root"""
        return self._registered_root or self.Session.get("AVALON_PROJECTS")

    def registered_host(self):
        """Return currently registered host"""
        return self._registered_host

    def register_host(self, host):
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

        self._validate_signature(host, signatures)
        self._registered_host = host

    def deregister_host(self):
        self._registered_host = None

    def registered_config(self):
        """Return currently registered config"""
        return self._registered_config

    def register_config(self, config):
        """Register a new config for the current process

        Arguments:
            config (ModuleType): A module implementing the Config API.

        """

        signatures = {
            "install": [],
            "uninstall": [],
        }

        self._validate_signature(config, signatures)
        self._registered_config = config

    def deregister_config(self):
        # TODO Global context
        """Undo `register_config()`"""
        self._registered_config = None

    def create(self, name, asset, family, options=None, data=None):
        """Create a new instance

        Associate nodes with a subset and family. These nodes are later
        validated, according to their `family`, and integrated into the
        shared environment, relative their `subset`.

        Data relative each family, along with default data, are imprinted
        into the resulting objectSet. This data is later used by extractors
        and finally asset browsers to help identify the origin of the asset.

        Arguments:
            name (str): Name of subset
            asset (str): Name of asset
            family (str): Name of family
            options (dict, optional): Additional options from GUI
            data (dict, optional): Additional data from GUI

        Raises:
            NameError on `subset` already exists
            KeyError on invalid dynamic property
            RuntimeError on host error

        Returns:
            Name of instance

        """

        host = self.registered_host()

        plugins = list()
        for Plugin in self.discover(api.Creator):
            if not family == Plugin.family:
                continue

            Plugin.log.info(
                "Creating '%s' with '%s'" % (name, Plugin.__name__)
            )

            try:
                plugin = Plugin(name, asset, options, data)

                with host.maintained_selection():
                    print("Running {}".format(plugin))
                    instance = plugin.process()

                plugins.append(plugin)

            except Exception:
                self.log.error(
                    "Creator failed {}".format(Plugin.__name__), exc_info=True
                )

        assert plugins, "No Creator plug-ins were run, this is a bug"
        return instance

    def update_current_task(self, task=None, asset=None, app=None):
        """Update active Session to a new task work area.

        This updates the live Session to a different `asset`, `task` or `app`.

        Args:
            task (str): The task to set.
            asset (str): The asset to set.
            app (str): The app to set.

        Returns:
            dict: The changed key, values in the current Session.

        """

        changes = pipeline.compute_session_changes(
            self.Session, task=task, asset=asset, app=app, dbcon=self.dbcon
        )

        # TODO do not set environments
        # Update the Session and environments. Pop from environments all keys
        # value set to None.
        for key, value in changes.items():
            self.Session[key] = value
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        # TODO ADD emmiting
        # # Emit session change
        # emit("taskChanged", changes.copy())

        return changes

    def load(
        self, Loader, representation,
        namespace=None, name=None, options=None, **kwargs
    ):
        """Use Loader to load a representation.

        Args:
            Loader (Loader): The loader class to trigger.
            representation (str or io.ObjectId or dict): The representation id
                or full representation as returned by the database.
            namespace (str, Optional): The namespace to assign.
                Defaults to None.
            name (str, Optional): The name to assign. Defaults to subset name.
            options (dict, Optional): Additional options to pass on to
                the loader.

        Returns:
            The return of the `loader.load()` method.

        Raises:
            IncompatibleLoaderError: When the loader is not compatible with
                the representation.

        """

        Loader = pipeline.make_backwards_compatible_loader(Loader)
        context = pipeline.get_representation_context(
            representation, self.dbcon
        )

        # Ensure the Loader is compatible for the representation
        if not pipeline.is_compatible_loader(Loader, context):
            raise pipeline.IncompatibleLoaderError(
                "Loader {} is incompatible with {}".format(
                    Loader.__name__, context["subset"]["name"]
                )
            )

        # Ensure options is a dictionary when no explicit options provided
        if options is None:
            options = kwargs.get("data", dict())  # "data" for backward compat

        assert isinstance(options, dict), "Options must be a dictionary"

        # Fallback to subset when name is None
        if name is None:
            name = context["subset"]["name"]

        self.log.info("Running '{}' on '{}'".format(
            Loader.__name__, context["asset"]["name"]
        ))

        loader = Loader(context)
        return loader.load(context, name, namespace, options)

    def _get_container_loader(self, container):
        """Return the Loader corresponding to the container"""

        loader = container["loader"]
        for Plugin in self.discover(api.Loader):
            # TODO: Ensure the loader is valid
            if Plugin.__name__ == loader:
                return Plugin

    def remove(self, container):
        """Remove a container"""

        Loader = self._get_container_loader(container)
        if not Loader:
            raise RuntimeError("Can't remove container. See log for details.")

        Loader = pipeline.make_backwards_compatible_loader(Loader)

        context = pipeline.get_representation_context(
            container["representation"], self.dbcon
        )
        loader = Loader(context)
        return loader.remove(container)

    def update(self, container, version=None):
        """Update a container."""
        if version is None:
            version = -1

        # Compute the different version from 'representation'
        current_representation = self.dbcon.find_one({
            "_id": ObjectId(container["representation"])
        })

        assert current_representation is not None, "This is a bug"

        current_version, subset, asset, project = self.dbcon.parenthood(
            current_representation
        )

        if version == -1:
            new_version = self.dbcon.find_one({
                "type": "version",
                "parent": subset["_id"]
            }, sort=[("name", -1)])
        else:
            if isinstance(version, lib.MasterVersionType):
                version_query = {
                    "parent": subset["_id"],
                    "type": "master_version"
                }
            else:
                version_query = {
                    "parent": subset["_id"],
                    "type": "version",
                    "name": version
                }
            new_version = self.dbcon.find_one(version_query)

        assert new_version is not None, "This is a bug"

        new_representation = self.dbcon.find_one({
            "type": "representation",
            "parent": new_version["_id"],
            "name": current_representation["name"]
        })

        # Run update on the Loader for this container
        Loader = self._get_container_loader(container)
        if not Loader:
            raise RuntimeError("Can't update container. See log for details.")

        context = pipeline.get_representation_context(
            container["representation"], self.dbcon
        )
        Loader = pipeline.make_backwards_compatible_loader(Loader)
        loader = Loader(context)

        return loader.update(container, new_representation)

    def switch(self, container, representation):
        """Switch a container to representation

        Args:
            container (dict): container information
            representation (dict): representation data from document

        Returns:
            function call
        """

        # Get the Loader for this container
        Loader = self._get_container_loader(container)

        if not Loader:
            raise RuntimeError("Can't switch container. See log for details.")

        if not hasattr(Loader, "switch"):
            # Backwards compatibility (classes without switch support
            # might be better to just have "switch" raise NotImplementedError
            # on the base class of Loader\
            raise RuntimeError("Loader '{}' does not support 'switch'".format(
                Loader.label
            ))

        # Get the new representation to switch to
        new_representation = self.dbcon.find_one({
            "type": "representation",
            "_id": representation["_id"],
        })

        new_context = pipeline.get_representation_context(
            new_representation, self.dbcon
        )
        assert pipeline.is_compatible_loader(Loader, new_context), (
            "Must be compatible Loader"
        )

        Loader = pipeline.make_backwards_compatible_loader(Loader)
        loader = Loader(new_context)

        return loader.switch(container, new_representation)

    def _validate_signature(self, module, signatures):
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

    def _install_sentry(self):
        sentry_url = self.Session.get("AVALON_SENTRY")
        if not sentry_url:
            return

        try:
            from raven import Client
            from raven.handlers.logging import SentryHandler
            from raven.conf import setup_logging
        except ImportError:
            # Note: There was a Sentry address in this Session
            return self.log.warning("Sentry disabled, raven not installed")

        client = Client(sentry_url)

        # Transmit log messages to Sentry
        handler = SentryHandler(client)
        handler.setLevel(logging.WARNING)

        setup_logging(handler)

        self._sentry_client = client
        self._sentry_logging_handler = handler
        self.log.info("Connected to Sentry @ {}".format(sentry_url))
