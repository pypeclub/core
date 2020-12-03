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
    """Yields containers from active AfterEffects document

    This is the host-equivalent of api.ls(), but instead of listing
    assets on disk, it lists assets already loaded in Photoshop; once loaded
    they are called 'containers'

    Yields:
        dict: container

    """
    try:
        stub = lib.stub()  # only after AfterEffects is up
    except lib.ConnectionNotEstablishedYet:
        print("Not connected yet, ignoring")
        return

    layers_meta = stub.get_metadata()
    for layer in stub.get_items(comps=True,
                                folders=False,
                                footages=True):
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
    """Imprint layer with metadata

    Containerisation enables a tracking of version, author and origin
    for loaded assets.

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
        "schema": "avalon-core:container-2.0",
        "id": pipeline.AVALON_CONTAINER_ID,
        "name": name,
        "namespace": namespace,
        "loader": str(loader),
        "representation": str(context["representation"]["_id"]),
    }

    stub = lib.stub()
    stub.imprint(comp, data)

    return comp
