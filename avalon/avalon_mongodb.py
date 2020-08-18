import sys
import time
import functools
import logging
import pymongo
from uuid import uuid4

from . import lib, schema


def extract_port_from_url(url):
    if sys.version_info[0] == 2:
        from urlparse import urlparse
    else:
        from urllib.parse import urlparse
    parsed_url = urlparse(url)
    if parsed_url.scheme is None:
        _url = "mongodb://{}".format(url)
        parsed_url = urlparse(_url)
    return parsed_url.port


def requires_install(func):
    @functools.wraps(func)
    def decorated(obj, *args, **kwargs):
        if not obj.installed:
            raise IOError("'{}.{}()' requires to run install() first".format(
                obj.__class__.__name__, func.__name__
            ))
        return func(obj, *args, **kwargs)
    return decorated


def auto_reconnect(func):
    """Handling auto reconnect in 3 retry times"""
    retry_times = 3
    reconnect_msg = "Reconnecting..."

    @functools.wraps(func)
    def decorated(obj, *args, **kwargs):
        for retry in range(1, retry_times + 1):
            try:
                return func(obj, *args, **kwargs)
            except pymongo.errors.AutoReconnect:
                if hasattr(obj, "log"):
                    obj.log.warning(reconnect_msg)
                else:
                    print(reconnect_msg)

                if retry >= retry_times:
                    raise
                time.sleep(0.1)
    return decorated


class AvalonMongoConnection:
    def __init__(self, session=None):
        self._id = uuid4()
        self._mongo_client = None
        self._database = None
        self._is_installed = False

        if session is None:
            session = lib.session_data_from_environment(context_keys=False)

        self.Session = session

        self.log = logging.getLogger(self.__class__.__name__)

    def __getattr__(self, attr_name):
        attr = None
        if self.is_installed:
            attr = getattr(
                self._database[self.active_project()],
                attr_name,
                None
            )

        if attr is None:
            # Reraise attribute error
            return self.__getattribute__(attr_name)

        # Decorate function
        if callable(attr):
            attr = auto_reconnect(attr)
        return attr

    def is_installed(self):
        return self._is_installed

    def install(self, update_context_from_env=False):
        """Establish a persistent connection to the database"""
        if update_context_from_env:
            self.Session.update(lib.session_data_from_environment(
                global_keys=False, context_keys=True
            ))

        if self.is_installed():
            return

        timeout = int(self.Session["AVALON_TIMEOUT"])
        mongo_url = self.Session["AVALON_MONGO"]
        kwargs = {
            "host": mongo_url,
            "serverSelectionTimeoutMS": timeout
        }

        port = extract_port_from_url(mongo_url)
        if port is not None:
            kwargs["port"] = int(port)

        self._mongo_client = pymongo.MongoClient(**kwargs)

        for retry in range(3):
            try:
                t1 = time.time()
                self._mongo_client.server_info()

            except Exception:
                self.log.warning("Retrying...")
                time.sleep(1)
                timeout *= 1.5

            else:
                break

        else:
            raise IOError((
                "ERROR: Couldn't connect to {} in less than {:.3f}ms"
            ).format(mongo_url, timeout))

        self.log.info("Connected to {}, delay {:.3f}s".format(
            mongo_url, time.time() - t1
        ))

        self._database = self._mongo_client[self.Session["AVALON_DB"]]
        self._is_installed = True

    def uninstall(self):
        """Close any connection to the database"""
        try:
            self._mongo_client.close()
        except AttributeError:
            pass

        self._mongo_client = None
        self._database = None
        self._is_installed = False

    @requires_install
    def active_project(self):
        """Return the name of the active project"""
        return self.Session["AVALON_PROJECT"]

    @requires_install
    def projects(self):
        """List available projects

        Returns:
            list of project documents

        """
        @auto_reconnect
        def find_project(project_name):
            return self._database[project_name].find_one({"type": "project"})

        @auto_reconnect
        def db_collections():
            return self._database.collection_names()

        for project in db_collections():
            if project in ("system.indexes",):
                continue

            # Each collection will have exactly one project document
            document = find_project(project)
            if document is not None:
                yield document

    @auto_reconnect
    def insert_one(self, item, *args, **kwargs):
        assert isinstance(item, dict), "item must be of type <dict>"
        schema.validate(item)
        return self._database[self.active_project()].insert_one(
            item, *args, **kwargs
        )

    @auto_reconnect
    def insert_many(self, items, *args, **kwargs):
        # check if all items are valid
        assert isinstance(items, list), "`items` must be of type <list>"
        for item in items:
            assert isinstance(item, dict), "`item` must be of type <dict>"
            schema.validate(item)

        return self._database[self.active_project()].insert_many(
            items, *args, **kwargs
        )

    def parenthood(self, document):
        assert document is not None, "This is a bug"

        parents = list()

        while document.get("parent") is not None:
            document = self.find_one({"_id": document["parent"]})
            if document is None:
                break

            if document.get("type") == "master_version":
                _document = self.find_one({"_id": document["version_id"]})
                document["data"] = _document["data"]

            parents.append(document)

        return parents

    def locate(self, path):
        """Traverse a hierarchy from top-to-bottom

        Example:
            representation = locate(["hulk", "Bruce", "modelDefault", 1, "ma"])

        Returns:
            representation (ObjectId)

        """

        components = zip(
            ("project", "asset", "subset", "version", "representation"),
            path
        )

        parent = None
        for type_, name in components:
            latest = (type_ == "version") and name in (None, -1)
            parent_filter = {
                "type": type_,
                "parent": parent
            }
            kwargs = {}
            if latest:
                kwargs["sort"] = [("name", -1)]
            else:
                parent_filter["name"] = name

            try:
                parent = self.find_one(parent_filter, **kwargs)["_id"]

            except TypeError:
                return None
        return parent
