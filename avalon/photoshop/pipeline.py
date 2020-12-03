from .. import api, pipeline
from . import lib
from ..vendor import Qt
from collections import namedtuple

import pyblish.api


def install():
    """Install Photoshop-specific functionality of avalon-core.

    This function is called automatically on calling `api.install(photoshop)`.
    """
    print("Installing Avalon Photoshop...")
    pyblish.api.register_host("photoshop")


def ls():
    """Yields containers from active Photoshop document

    This is the host-equivalent of api.ls(), but instead of listing
    assets on disk, it lists assets already loaded in Photoshop; once loaded
    they are called 'containers'

    Yields:
        dict: container

    """
    try:
        stub = lib.stub()  # only after Photoshop is up
    except lib.ConnectionNotEstablishedYet:
        print("Not connected yet, ignoring")
        return

    if not stub.get_active_document_name():
        return

    layers_meta = stub.get_layers_metadata()  # minimalize calls to PS
    for layer in stub.get_layers():
        data = stub.read(layer, layers_meta)

        # Skip non-tagged layers.
        if not data:
            continue

        # Filter to only containers.
        if "container" not in data["id"]:
            continue

        # Append transient data
        data["layer"] = layer

        yield data


class Creator(api.Creator):
    """Creator plugin to create instances in Photoshop

    A LayerSet is created to support any number of layers in an instance. If
    the selection is used, these layers will be added to the LayerSet.
    """

    def process(self):
        # Photoshop can have multiple LayerSets with the same name, which does
        # not work with Avalon.
        msg = "Instance with name \"{}\" already exists.".format(self.name)
        stub = lib.stub()  # only after Photoshop is up
        for layer in stub.get_layers():
            if self.name.lower() == layer.Name.lower():
                msg = Qt.QtWidgets.QMessageBox()
                msg.setIcon(Qt.QtWidgets.QMessageBox.Warning)
                msg.setText(msg)
                msg.exec_()
                return False

        group = None
        # Store selection because adding a group will change selection.
        with lib.maintained_selection():

            # Add selection to group.
            if (self.options or {}).get("useSelection"):
                group = stub.group_selected_layers(self.name)
            else:
                group = stub.create_group(self.name)

            stub.imprint(group, self.data)

        return group


def containerise(name,
                 namespace,
                 layer,
                 context,
                 loader=None,
                 suffix="_CON"):
    """Imprint layer with metadata

    Containerisation enables a tracking of version, author and origin
    for loaded assets.

    Arguments:
        name (str): Name of resulting assembly
        namespace (str): Namespace under which to host container
        layer (Layer): Layer to containerise
        context (dict): Asset information
        loader (str, optional): Name of loader used to produce this container.
        suffix (str, optional): Suffix of container, defaults to `_CON`.

    Returns:
        container (str): Name of container assembly
    """
    # layer is namedtuple - immutable - need to change to dict and back
    # refactor to proper object
    layer = layer._asdict()
    layer["name"] = name + suffix
    layer = namedtuple('Layer', layer.keys())(*layer.values())

    data = {
        "schema": "avalon-core:container-2.0",
        "id": pipeline.AVALON_CONTAINER_ID,
        "name": name,
        "namespace": namespace,
        "loader": str(loader),
        "representation": str(context["representation"]["_id"]),
    }
    stub = lib.stub()
    stub.imprint(layer, data)

    return layer
