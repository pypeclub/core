import logging
import collections

from ....vendor import qtawesome
from ....vendor.Qt import QtCore, QtGui

from .... import io, style
from . import TreeModel, Node

log = logging.getLogger(__name__)


class AssetModel(TreeModel):
    """ Displaying assets in hierarchical tree by visualParent.

    The assets are displayed in a treeview, they are visually parented by
    a `visualParent` field in the database containing an `_id` to a parent
    asset.

    Entities with `visualParent` set to None/null/nil are used as top items.
    """

    COLUMNS = ["label"]
    Name = 0
    Deprecated = 2
    ObjectId = 3

    DocumentRole = QtCore.Qt.UserRole + 2
    ObjectIdRole = QtCore.Qt.UserRole + 3
    subsetColorsRole = QtCore.Qt.UserRole + 4

    def __init__(self, parent=None):
        super(AssetModel, self).__init__(parent=parent)
        self.asset_colors = {}
        self.refresh()

    def _add_hierarchy(self, assets, parent=None):
        """Add the assets that are related to the parent as children items.

        This method does *not* query the database. These instead are queried
        in a single batch upfront as an optimization to reduce database
        queries. Resulting in up to 10x speed increase.

        Args:
            assets (dict): All assets in the currently active silo stored
                by key/value

        Returns:
            None

        """
        # Reset colors
        self.asset_colors = {}
        
        parent_id = parent["_id"] if parent else None
        current_assets = assets.get(parent_id, list())

        for asset in current_assets:
            # get label from data, otherwise use name
            data = asset.get("data", {})
            label = data.get("label", asset["name"])
            tags = data.get("tags", [])

            # store for the asset for optimization
            deprecated = "deprecated" in tags

            node = Node({
                "_id": asset["_id"],
                "name": asset["name"],
                "label": label,
                "type": asset["type"],
                "tags": ", ".join(tags),
                "deprecated": deprecated,
                "_document": asset
            })
            self.add_child(node, parent=parent)

            # Add asset's children recursively if it has children
            if asset["_id"] in assets:
                self._add_hierarchy(assets, parent=node)

            self.asset_colors[asset["_id"]] = []

    def refresh(self):
        """Refresh the data for the model."""

        self.clear()
        self.beginResetModel()

        db_assets = io.find({
            "type": "asset"
        }).sort("name", 1)

        # Group the assets by their visual parent's id
        assets_by_parent = collections.defaultdict(list)
        for asset in db_assets:
            parent_id = asset.get("data", {}).get("visualParent") or None
            assets_by_parent[parent_id].append(asset)

        # Build the hierarchical tree items recursively
        self._add_hierarchy(
            assets_by_parent, parent=None
        )

        self.endResetModel()

    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid():
            return False

        if role == self.subsetColorsRole:
            asset_id = index.data(self.ObjectIdRole)
            self.asset_colors[asset_id] = value

            # passing `list()` for PyQt5 (see PYSIDE-462)
            self.dataChanged.emit(index, index, list())

            return True

        return super(AssetModel, self).setData(index, value, role)

    def data(self, index, role):
        if not index.isValid():
            return

        node = index.internalPointer()
        if role == QtCore.Qt.DecorationRole:        # icon

            column = index.column()
            if column == self.Name:

                # Allow a custom icon and custom icon color to be defined
                data = node["_document"]["data"]
                icon = data.get("icon", None)
                color = data.get("color", style.colors.default)

                if icon is None:
                    # Use default icons if no custom one is specified.
                    # If it has children show a full folder, otherwise
                    # show an open folder
                    has_children = self.rowCount(index) > 0
                    icon = "folder" if has_children else "folder-o"

                # Make the color darker when the asset is deprecated
                if node.get("deprecated", False):
                    color = QtGui.QColor(color).darker(250)

                try:
                    key = "fa.{0}".format(icon)  # font-awesome key
                    icon = qtawesome.icon(key, color=color)
                    return icon
                except Exception as exception:
                    # Log an error message instead of erroring out completely
                    # when the icon couldn't be created (e.g. invalid name)
                    log.error(exception)

                return

        if role == QtCore.Qt.ForegroundRole:        # font color
            if "deprecated" in node.get("tags", []):
                return QtGui.QColor(style.colors.light).darker(250)

        if role == self.ObjectIdRole:
            return node.get("_id", None)

        if role == self.DocumentRole:
            return node.get("_document", None)

        if role == self.subsetColorsRole:
            asset_id = node.get("_id", None)
            if not asset_id:
                return []
            return self.asset_colors.get(asset_id) or []

        return super(AssetModel, self).data(index, role)
