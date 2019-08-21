from ....vendor import qtawesome
from ....vendor.Qt import QtCore

from .... import io, style

from . import Node, TreeModel
from . import lib
from .. import lib as gui_lib


class SubsetModel(TreeModel):
    COLUMNS = [
        "subset",
        "asset",
        "family",
        "version",
        "time",
        "author",
        "frames",
        "duration",
        "handles",
        "step"
    ]

    column_labels_mapping = {
        "subset": "Subset",
        "asset": "Asset",
        "family": "Family",
        "version": "Version",
        "time": "Time",
        "author": "Author",
        "frames": "Frames",
        "duration": "Duration",
        "handles": "Handles",
        "step": "Step"
    }

    SortAscendingRole = QtCore.Qt.UserRole + 2
    SortDescendingRole = QtCore.Qt.UserRole + 3
    merged_subset_colors = [
        (55, 161, 222), # Light Blue
        (231, 176, 0), # Yellow
        (154, 13, 255), # Purple
        (130, 184, 30), # Light Green
        (211, 79, 63), # Light Red
        (179, 181, 182), # Grey
        (194, 57, 179), # Pink
        (0, 120, 215), # Dark Blue
        (0, 204, 106), # Dark Green
        (247, 99, 12), # Orange
    ]

    def __init__(self, grouping=True, parent=None):
        super(SubsetModel, self).__init__(parent=parent)
        self._asset_ids = None
        self._sorter = None
        self._grouping = grouping
        self._icons = {
            "subset": qtawesome.icon("fa.file-o", color=style.colors.default)
        }

    def set_assets(self, asset_ids):
        self._asset_ids = asset_ids
        self.refresh()

    def set_grouping(self, state):
        self._grouping = state
        self.refresh()

    def setData(self, index, value, role=QtCore.Qt.EditRole):

        # Trigger additional edit when `version` column changed
        # because it also updates the information in other columns
        if index.column() == self.COLUMNS.index("version"):
            node = index.internalPointer()
            parent = node["_id"]
            version = io.find_one({
                "name": value,
                "type": "version",
                "parent": parent
            })
            self.set_version(index, version)

        return super(SubsetModel, self).setData(index, value, role)

    def set_version(self, index, version):
        """Update the version data of the given index.

        Arguments:
            version (dict) Version document in the database. """

        assert isinstance(index, QtCore.QModelIndex)
        if not index.isValid():
            return

        node = index.internalPointer()
        assert version['parent'] == node['_id'], (
            "Version does not belong to subset"
        )

        # Get the data from the version
        version_data = version.get("data", dict())

        # Compute frame ranges (if data is present)
        start = version_data.get("frameStart", None)
        end = version_data.get("frameEnd", None)
        handles = version_data.get("handles", None)
        if start is not None and end is not None:
            # Remove superfluous zeros from numbers (3.0 -> 3) to improve
            # readability for most frame ranges
            start_clean = ('%f' % start).rstrip('0').rstrip('.')
            end_clean = ('%f' % end).rstrip('0').rstrip('.')
            frames = "{0}-{1}".format(start_clean, end_clean)
            duration = end - start + 1
        else:
            frames = None
            duration = None

        families = version_data.get("families", [None])
        family = families[0]
        family_config = gui_lib.get(gui_lib.FAMILY_CONFIG, family)

        node.update({
            "version": version['name'],
            "version_document": version,
            "author": version_data.get("author", None),
            "time": version_data.get("time", None),
            "family": family,
            "familyLabel": family_config.get("label", family),
            "familyIcon": family_config.get('icon', None),
            "families": set(families),
            "frameStart": start,
            "frameEnd": end,
            "duration": duration,
            "handles": handles,
            "frames": frames,
            "step": version_data.get("step", None)
        })

    def refresh(self):
        self.clear()
        self.beginResetModel()
        if not self._asset_ids:
            self.endResetModel()
            return

        active_groups = []
        for asset_id in self._asset_ids:
            result = lib.get_active_group_config(asset_id)
            if result:
                active_groups.extend(result)

        parent_filter = [{"parent": asset_id} for asset_id in self._asset_ids]
        filtered_subsets = [
            s for s in io.find({"type": "subset", "$or": parent_filter})
        ]

        asset_entities = {}
        for asset_id in self._asset_ids:
            asset_ent = io.find_one({"_id": asset_id})
            asset_entities[asset_id] = asset_ent

        # Collect last versions
        last_versions = {}
        for subset in filtered_subsets:
            last_version = io.find_one({
                "type": "version",
                "parent": subset["_id"]
            }, sort=[("name", -1)])
            # No published version for the subset
            last_versions[subset["_id"]] = last_version

        # Prepare data if is selected more than one asset
        process_only_single_asset = True
        merge_subsets = False
        if len(parent_filter) >= 2:
            process_only_single_asset = False
            all_subset_names = []
            multiple_asset_names = []

            for subset in filtered_subsets:
                # No published version for the subset
                if not last_versions[subset["_id"]]:
                    continue

                name = subset["name"]
                if name in all_subset_names:
                    # process_only_single_asset = False
                    merge_subsets = True
                    if name not in multiple_asset_names:
                        multiple_asset_names.append(name)
                else:
                    all_subset_names.append(name)

        # Process subsets
        row = 0
        group_nodes = dict()

        # When only one asset is selected
        if process_only_single_asset:
            if self._grouping:
                # Generate subset group nodes
                group_names = []
                for data in active_groups:
                    name = data.pop("name")
                    if name in group_names:
                        continue
                    group_names.append(name)

                    group = Node()
                    group.update({
                        "subset": name,
                        "isGroup": True,
                        "childRow": 0
                    })
                    group.update(data)

                    group_nodes[name] = group
                    self.add_child(group)

            row = len(group_nodes)
            single_asset_subsets = filtered_subsets

        # When multiple assets are selected
        else:
            single_asset_subsets = []
            multi_asset_subsets = {}

            for subset in filtered_subsets:
                last_version = last_versions[subset["_id"]]
                if not last_version:
                    continue

                data = subset.copy()

                name = data["name"]
                asset_name = asset_entities[data["parent"]]["name"]

                data["subset"] = name
                data["asset"] = asset_name

                asset_subset_data = {
                    "data": data,
                    "last_version": last_version
                }

                if name in multiple_asset_names:
                    if name not in multi_asset_subsets:
                        multi_asset_subsets[name] = {}
                    multi_asset_subsets[name][data["parent"]] = (
                        asset_subset_data
                    )
                else:
                    single_asset_subsets.append(data)

            color_count = len(self.merged_subset_colors)
            merged_names = {}
            subset_counter = 0
            total = len(multi_asset_subsets)
            str_order_temp = "%0{}d".format(len(str(total)))

            for subset_name, per_asset_data in multi_asset_subsets.items():
                subset_color = self.merged_subset_colors[
                    subset_counter%color_count
                ]
                inverse_order = total - subset_counter

                merge_group = Node()
                merge_group.update({
                    "subset": "{} ({})".format(
                        subset_name, str(len(per_asset_data))
                    ),
                    "isMerged": True,
                    "childRow": 0,
                    "subsetColor": subset_color,
                    "assetIds": [id for id in per_asset_data],

                    "icon": qtawesome.icon(
                        "fa.circle",
                        color="#{0:02x}{1:02x}{2:02x}".format(*subset_color)
                    ),
                    "order": "0{}".format(subset_name),
                    "inverseOrder": str_order_temp % inverse_order
                })

                subset_counter += 1
                row += 1
                group_nodes[subset_name] = merge_group
                self.add_child(merge_group)

                merge_group_index = self.createIndex(0, 0, merge_group)

                for asset_id, asset_subset_data in per_asset_data.items():
                    last_version = asset_subset_data["last_version"]
                    data = asset_subset_data["data"]

                    row_ = merge_group["childRow"]
                    merge_group["childRow"] += 1

                    node = Node()
                    node.update(data)

                    self.add_child(node, parent=merge_group)

                    # Set the version information
                    index = self.index(row_, 0, parent=merge_group_index)
                    self.set_version(index, last_version)

        for subset in single_asset_subsets:
            last_version = last_versions[subset["_id"]]
            if not last_version:
                continue

            data = subset.copy()
            data["subset"] = data["name"]

            group_name = subset["data"].get("subsetGroup")
            if process_only_single_asset:
                if self._grouping and group_name:
                    group = group_nodes[group_name]
                    parent = group
                    parent_index = self.createIndex(0, 0, group)
                    row_ = group["childRow"]
                    group["childRow"] += 1
                else:
                    parent = None
                    parent_index = QtCore.QModelIndex()
                    row_ = row
                    row += 1
            else:
                parent = None
                parent_index = QtCore.QModelIndex()
                row_ = row
                row += 1

            node = Node()
            node.update(data)

            self.add_child(node, parent=parent)

            # Set the version information
            index = self.index(row_, 0, parent=parent_index)
            self.set_version(index, last_version)

        self.endResetModel()

    def data(self, index, role):
        if not index.isValid():
            return

        if role == QtCore.Qt.DisplayRole:
            if index.column() == self.COLUMNS.index("family"):
                # Show familyLabel instead of family
                node = index.internalPointer()
                return node.get("familyLabel", None)

        if role == QtCore.Qt.DecorationRole:
            # Add icon to subset column
            if index.column() == self.COLUMNS.index("subset"):
                node = index.internalPointer()
                if node.get("isGroup") or node.get("isMerged"):
                    return node["icon"]
                else:
                    return self._icons["subset"]

            # Add icon to family column
            if index.column() == self.COLUMNS.index("family"):
                node = index.internalPointer()
                return node.get("familyIcon", None)

        if role == self.SortDescendingRole:
            node = index.internalPointer()
            if node.get("isGroup") or node.get("isMerged"):
                # Ensure groups be on top when sorting by descending order
                prefix = "1"
                order = node["inverseOrder"]
            else:
                prefix = "0"
                order = str(
                    super(SubsetModel, self).data(index, QtCore.Qt.DisplayRole)
                )
            return prefix + order

        if role == self.SortAscendingRole:
            node = index.internalPointer()
            if node.get("isGroup") or node.get("isMerged"):
                # Ensure groups be on top when sorting by ascending order
                prefix = "0"
                order = node["order"]
            else:
                prefix = "1"
                order = str(
                    super(SubsetModel, self).data(index, QtCore.Qt.DisplayRole)
                )
            return prefix + order

        return super(SubsetModel, self).data(index, role)

    def flags(self, index):
        flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

        # Make the version column editable
        if index.column() == 2:  # version column
            flags |= QtCore.Qt.ItemIsEditable

        return flags

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole:
            if section < len(self.COLUMNS):
                key = self.COLUMNS[section]
                return self.column_labels_mapping.get(key) or key

        super(TreeModel, self).headerData(section, orientation, role)
