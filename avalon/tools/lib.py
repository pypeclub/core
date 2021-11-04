import os
import sys
import contextlib
import collections

from .. import io, api, style
from ..vendor import qtawesome

from ..vendor.Qt import QtWidgets, QtCore, QtGui

self = sys.modules[__name__]
self._jobs = dict()
self._path = os.path.dirname(__file__)

# Variable for family cache in global context
# QUESTION is this safe? More than one tool can refresh at the same time.
_GLOBAL_FAMILY_CACHE = None


def global_family_cache():
    global _GLOBAL_FAMILY_CACHE
    if _GLOBAL_FAMILY_CACHE is None:
        _GLOBAL_FAMILY_CACHE = FamilyConfigCache(io)
    return _GLOBAL_FAMILY_CACHE


def format_version(value, hero_version=False):
    """Formats integer to displayable version name"""
    label = "v{0:03d}".format(value)
    if not hero_version:
        return label
    return "[{}]".format(label)


def resource(*path):
    path = os.path.join(self._path, "_res", *path)
    return path.replace("\\", "/")


@contextlib.contextmanager
def application():
    app = QtWidgets.QApplication.instance()

    if not app:
        print("Starting new QApplication..")
        app = QtWidgets.QApplication(sys.argv)
        yield app
        app.exec_()
    else:
        print("Using existing QApplication..")
        yield app


def schedule(func, time, channel="default"):
    """Run `func` at a later `time` in a dedicated `channel`

    Given an arbitrary function, call this function after a given
    timeout. It will ensure that only one "job" is running within
    the given channel at any one time and cancel any currently
    running job if a new job is submitted before the timeout.

    """

    try:
        self._jobs[channel].stop()
    except (AttributeError, KeyError, RuntimeError):
        pass

    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(func)
    timer.start(time)

    self._jobs[channel] = timer


def iter_model_rows(model, column, include_root=False):
    """Iterate over all row indices in a model"""
    indices = [QtCore.QModelIndex()]  # start iteration at root

    for index in indices:
        # Add children to the iterations
        child_rows = model.rowCount(index)
        for child_row in range(child_rows):
            child_index = model.index(child_row, column, index)
            indices.append(child_index)

        if not include_root and not index.isValid():
            continue

        yield index


@contextlib.contextmanager
def preserve_expanded_rows(tree_view, column=0, role=None):
    """Preserves expanded row in QTreeView by column's data role.

    This function is created to maintain the expand vs collapse status of
    the model items. When refresh is triggered the items which are expanded
    will stay expanded and vise versa.

    Arguments:
        tree_view (QWidgets.QTreeView): the tree view which is
            nested in the application
        column (int): the column to retrieve the data from
        role (int): the role which dictates what will be returned

    Returns:
        None

    """
    if role is None:
        role = QtCore.Qt.DisplayRole
    model = tree_view.model()

    expanded = set()

    for index in iter_model_rows(model, column=column, include_root=False):
        if tree_view.isExpanded(index):
            value = index.data(role)
            expanded.add(value)

    try:
        yield
    finally:
        if not expanded:
            return

        for index in iter_model_rows(model, column=column, include_root=False):
            value = index.data(role)
            state = value in expanded
            if state:
                tree_view.expand(index)
            else:
                tree_view.collapse(index)


@contextlib.contextmanager
def preserve_selection(tree_view, column=0, role=None, current_index=True):
    """Preserves row selection in QTreeView by column's data role.

    This function is created to maintain the selection status of
    the model items. When refresh is triggered the items which are expanded
    will stay expanded and vise versa.

        tree_view (QWidgets.QTreeView): the tree view nested in the application
        column (int): the column to retrieve the data from
        role (int): the role which dictates what will be returned

    Returns:
        None

    """
    if role is None:
        role = QtCore.Qt.DisplayRole
    model = tree_view.model()
    selection_model = tree_view.selectionModel()
    flags = selection_model.Select | selection_model.Rows

    if current_index:
        current_index_value = tree_view.currentIndex().data(role)
    else:
        current_index_value = None

    selected_rows = selection_model.selectedRows()
    if not selected_rows:
        yield
        return

    selected = set(row.data(role) for row in selected_rows)
    try:
        yield
    finally:
        if not selected:
            return

        # Go through all indices, select the ones with similar data
        for index in iter_model_rows(model, column=column, include_root=False):
            value = index.data(role)
            state = value in selected
            if state:
                tree_view.scrollTo(index)  # Ensure item is visible
                selection_model.select(index, flags)

            if current_index_value and value == current_index_value:
                selection_model.setCurrentIndex(
                    index, selection_model.NoUpdate
                )


class FamilyConfigCache:
    default_color = "#0091B2"
    _default_icon = None
    _default_item = None

    def __init__(self, dbcon):
        self.dbcon = dbcon
        self.family_configs = {}

    @classmethod
    def default_icon(cls):
        if cls._default_icon is None:
            cls._default_icon = qtawesome.icon(
                "fa.folder", color=cls.default_color
            )
        return cls._default_icon

    @classmethod
    def default_item(cls):
        if cls._default_item is None:
            cls._default_item = {"icon": cls.default_icon()}
        return cls._default_item

    def family_config(self, family_name):
        """Get value from config with fallback to default"""
        return self.family_configs.get(family_name, self.default_item())

    def refresh(self):
        """Get the family configurations from the database

        The configuration must be stored on the project under `config`.
        For example:

        {"config": {
            "families": [
                {"name": "avalon.camera", label: "Camera", "icon": "photo"},
                {"name": "avalon.anim", label: "Animation", "icon": "male"},
            ]
        }}

        It is possible to override the default behavior and set specific
        families checked. For example we only want the families imagesequence
        and camera to be visible in the Loader.

        # This will turn every item off
        api.data["familyStateDefault"] = False

        # Only allow the imagesequence and camera
        api.data["familyStateToggled"] = ["imagesequence", "camera"]

        """

        self.family_configs.clear()

        families = []

        # Update the icons from the project configuration
        project_name = self.dbcon.Session.get("AVALON_PROJECT")
        if project_name:
            project_doc = self.dbcon.find_one(
                {"type": "project"},
                projection={"config.families": True}
            )

            if not project_doc:
                print((
                    "Project \"{}\" not found!"
                    " Can't refresh family icons cache."
                ).format(project_name))
            else:
                families = project_doc["config"].get("families") or []

        # Check if any family state are being overwritten by the configuration
        default_state = api.data.get("familiesStateDefault", True)
        toggled = set(api.data.get("familiesStateToggled") or [])

        # Replace icons with a Qt icon we can use in the user interfaces
        for family in families:
            name = family["name"]
            # Set family icon
            icon = family.get("icon", None)
            if icon:
                family["icon"] = qtawesome.icon(
                    "fa.{}".format(icon),
                    color=self.default_color
                )
            else:
                family["icon"] = self.default_icon()

            # Update state
            if name in toggled:
                state = True
            else:
                state = default_state
            family["state"] = state

            self.family_configs[name] = family

        return self.family_configs


def get_repre_icons():
    try:
        from openpype_modules import sync_server
    except Exception:
        # Backwards compatibility
        from openpype.modules import sync_server

    resource_path = os.path.join(
        os.path.dirname(sync_server.sync_server_module.__file__),
        "providers", "resources"
    )
    icons = {}
    # TODO get from sync module
    for provider in ['studio', 'local_drive', 'gdrive']:
        pix_url = "{}/{}.png".format(resource_path, provider)
        icons[provider] = QtGui.QIcon(pix_url)

    return icons


def get_progress_for_repre(doc, active_site, remote_site):
    """
        Calculates average progress for representation.

        If site has created_dt >> fully available >> progress == 1

        Could be calculated in aggregate if it would be too slow
        Args:
            doc(dict): representation dict
        Returns:
            (dict) with active and remote sites progress
            {'studio': 1.0, 'gdrive': -1} - gdrive site is not present
                -1 is used to highlight the site should be added
            {'studio': 1.0, 'gdrive': 0.0} - gdrive site is present, not
                uploaded yet
    """
    progress = {active_site: -1,
                remote_site: -1}
    if not doc:
        return progress

    files = {active_site: 0, remote_site: 0}
    doc_files = doc.get("files") or []
    for doc_file in doc_files:
        if not isinstance(doc_file, dict):
            continue

        sites = doc_file.get("sites") or []
        for site in sites:
            if (
                # Pype 2 compatibility
                not isinstance(site, dict)
                # Check if site name is one of progress sites
                or site["name"] not in progress
            ):
                continue

            files[site["name"]] += 1
            norm_progress = max(progress[site["name"]], 0)
            if site.get("created_dt"):
                progress[site["name"]] = norm_progress + 1
            elif site.get("progress"):
                progress[site["name"]] = norm_progress + site["progress"]
            else:  # site exists, might be failed, do not add again
                progress[site["name"]] = 0

    # for example 13 fully avail. files out of 26 >> 13/26 = 0.5
    avg_progress = {}
    avg_progress[active_site] = \
        progress[active_site] / max(files[active_site], 1)
    avg_progress[remote_site] = \
        progress[remote_site] / max(files[remote_site], 1)
    return avg_progress
