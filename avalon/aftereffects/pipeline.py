from .. import api, pipeline
from . import lib
from ..vendor import Qt

import pyblish.api
import logging
log = logging.getLogger(__name__)


def install():
    """Install After Effects-specific functionality of avalon-core.

    This function is called automatically on calling `api.install(photoshop)`.
    """
    print("Installing Avalon AfterEffects...")
    pyblish.api.register_host("aftereffects")


def ls():
    """Yields containers from active AfterEffects document.

    This is the host-equivalent of api.ls(), but instead of listing
    assets on disk, it lists assets already loaded in AE; once loaded
    they are called 'containers'. Used in Manage tool.

    Containers could be on multiple levels, single images/videos/was as a
    FootageItem, or multiple items - backgrounds (folder with automatically
    created composition and all imported layers).

    Yields:
        dict: container

    """
    try:
        stub = lib.stub()  # only after AfterEffects is up
    except lib.ConnectionNotEstablishedYet:
        print("Not connected yet, ignoring")
        return

    layers_meta = stub.get_metadata()
    for item in stub.get_items(comps=True,
                               folders=True,
                               footages=True):
        data = stub.read(item, layers_meta)
        # Skip non-tagged layers.
        if not data:
            continue

        # Filter to only containers.
        if "container" not in data["id"]:
            continue

        # Append transient data
        data["objectName"] = item.name.replace(stub.LOADED_ICON, '')
        data["layer"] = item
        yield data


def list_instances():
    """
        List all created instances from current workfile which
        will be published.

        Pulls from File > File Info

        For SubsetManager

        Returns:
            (list) of dictionaries matching instances format
    """
    stub = _get_stub()
    if not stub:
        return []

    instances = []
    layers_meta = stub.get_metadata()

    for instance in layers_meta:
        if instance.get("schema") and \
                "container" in instance.get("schema"):
            continue

        uuid_val = instance.get("uuid")
        if uuid_val:
            instance['uuid'] = uuid_val
        else:
            instance['uuid'] = instance.get("members")[0]  # legacy
        instances.append(instance)
    return instances


def remove_instance(instance):
    """
        Remove instance from current workfile metadata.

        Updates metadata of current file in File > File Info and removes
        icon highlight on group layer.

        For SubsetManager

        Args:
            instance (dict): instance representation from subsetmanager model
    """
    stub = _get_stub()

    if not stub:
        return

    stub.remove_instance(instance.get("uuid"))
    item = stub.get_item(instance.get("uuid"))
    if item:
        stub.rename_item(item.id,
                         item.name.replace(stub.PUBLISH_ICON, ''))

def _get_stub():
    """
        Handle pulling stub from PS to run operations on host
    Returns:
        (AEServerStub) or None
    """
    try:
        stub = lib.stub()  # only after Photoshop is up
    except lib.ConnectionNotEstablishedYet:
        print("Not connected yet, ignoring")
        return

    if not stub.get_active_document_name():
        return

    return stub


class Creator(api.Creator):
    """Creator plugin to create instances in After Effects

    A LayerSet is created to support any number of layers in an instance. If
    the selection is used, these layers will be added to the LayerSet.
    """

    def process(self):
        # Photoshop can have multiple LayerSets with the same name, which does
        # not work with Avalon.
        txt = "Instance with name \"{}\" already exists.".format(self.name)
        stub = lib.stub()  # only after After Effects is up
        for layer in stub.get_items(comps=True,
                                    folders=False,
                                    footages=False):
            if self.name.lower() == layer.name.lower():
                msg = Qt.QtWidgets.QMessageBox()
                msg.setIcon(Qt.QtWidgets.QMessageBox.Warning)
                msg.setText(txt)
                msg.exec_()
                return False

        if (self.options or {}).get("useSelection"):
            items = stub.get_selected_items(comps=True,
                                            folders=False,
                                            footages=False)
        else:
            items = stub.get_items(comps=True,
                                   folders=False,
                                   footages=False)

        for item in items:
            stub.imprint(item, self.data)


def containerise(name,
                 namespace,
                 comp,
                 context,
                 loader=None,
                 suffix="_CON"):
    """
    Containerisation enables a tracking of version, author and origin
    for loaded assets.

    Creates dictionary payloads that gets saved into file metadata. Each
    container contains of who loaded (loader) and members (single or multiple
    in case of background).

    Arguments:
        name (str): Name of resulting assembly
        namespace (str): Namespace under which to host container
        comp (Comp): Composition to containerise
        context (dict): Asset information
        loader (str, optional): Name of loader used to produce this container.
        suffix (str, optional): Suffix of container, defaults to `_CON`.

    Returns:
        container (str): Name of container assembly
    """
    data = {
        "schema": "openpype:container-2.0",
        "id": pipeline.AVALON_CONTAINER_ID,
        "name": name,
        "namespace": namespace,
        "loader": str(loader),
        "representation": str(context["representation"]["_id"]),
        "members": comp.members or [comp.id]
    }

    stub = lib.stub()
    stub.imprint(comp, data)

    return comp
