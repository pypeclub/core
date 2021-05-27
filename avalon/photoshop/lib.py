import os
import sys
import contextlib
import subprocess
import importlib
import logging
import functools
import time
import traceback

from wsrpc_aiohttp import (
    WebSocketRoute,
    WebSocketAsync
)

from Qt import QtWidgets, QtCore, QtGui

from avalon.tools.webserver.app import WebServerTool

from openpype.tools import workfiles
from openpype.tools.tray_app.app import TrayApp

from .ws_stub import PhotoshopServerStub

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def show(module_name):
    """Call show on "module_name".

    This allows to make a QApplication ahead of time and always "exec_" to
    prevent crashing.

    Args:
        module_name (str): Name of module to call "show" on.
    """
    if module_name == "workfiles":
        # Use Pype's workfiles tool
        tool_module = workfiles
    else:
        # Import and show tool.
        tool_module = importlib.import_module("avalon.tools." + module_name)

    if "loader" in module_name:
        tool_module.show(use_context=True)
    else:
        tool_module.show()


class ConnectionNotEstablishedYet(Exception):
    pass


class PhotoshopRoute(WebSocketRoute):
    """
        One route, mimicking external application (like Harmony, etc).
        All functions could be called from client.
        'do_notify' function calls function on the client - mimicking
            notification after long running job on the server or similar
    """
    instance = None

    def init(self, **kwargs):
        # Python __init__ must be return "self".
        # This method might return anything.
        log.debug("someone called Photoshop route")
        self.instance = self
        return kwargs

    # server functions
    async def ping(self):
        log.debug("someone called Photoshop route ping")

    # This method calls function on the client side
    # client functions

    async def read(self):
        log.debug("photoshop.read client calls server server calls "
                  "Photo client")
        return await self.socket.call('Photoshop.read')

    # panel routes for tools
    async def creator_route(self):
        self._tool_route("creator")

    async def workfiles_route(self):
        self._tool_route("workfiles")

    async def loader_route(self):
        self._tool_route("loader")

    async def publish_route(self):
        self._tool_route("publish")

    async def sceneinventory_route(self):
        self._tool_route("sceneinventory")

    async def subsetmanager_route(self):
        self._tool_route("subsetmanager")

    def _tool_route(self, tool_name):
        """The address accessed when clicking on the buttons."""
        partial_method = functools.partial(show, tool_name)

        TrayApp.execute_in_main_thread(partial_method)

        # Required return statement.
        return "nothing"


def stub():
    """
        Convenience function to get server RPC stub to call methods directed
        for host (Photoshop).
        It expects already created connection, started from client.
        Currently created when panel is opened (PS: Window>Extensions>Avalon)
    :return: <PhotoshopClientStub> where functions could be called from
    """
    stub = PhotoshopServerStub()
    if not stub.client:
        raise ConnectionNotEstablishedYet("Connection is not created yet")

    return stub


def safe_excepthook(*args):
    traceback.print_exception(*args)


def main(*subprocess_args):
    os.environ["OPENPYPE_LOG_NO_COLORS"] = "False"  # coloring in TrayApp
    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)

    trayApp = TrayApp('photoshop')
    trayApp.launch_method = launch
    trayApp.subprocess_args = subprocess_args

    sys.exit(app.exec_())


def launch(*subprocess_args):
    """Starts the websocket server that will be hosted
       in the Photoshop extension.
    """
    from avalon import api, photoshop

    api.install(photoshop)
    sys.excepthook = safe_excepthook
    # Launch Photoshop and the websocket server.
    TrayApp.process = subprocess.Popen(subprocess_args, stdout=subprocess.PIPE)

    websocket_server = WebServerTool()
    # Add Websocket route
    websocket_server.add_route("*", "/ws/", WebSocketAsync)
    # Add after effects route to websocket handler
    route_name = 'Photoshop'
    print("Adding {} route".format(route_name))
    WebSocketAsync.add_route(
        route_name, PhotoshopRoute  # keep same name as in extension
    )
    websocket_server.start_server()

    TrayApp.websocket_server = websocket_server

    while True:
        # add timeout
        if TrayApp.process.poll() is not None:
            print("Photoshop process is not alive. Exiting")
            TrayApp.websocket_server.stop()
            sys.exit(1)
        try:
            _stub = photoshop.stub()
            if _stub:
                break
        except Exception:
            time.sleep(0.5)

    # Photoshop could be closed immediately, withou workfile selection
    try:
        if photoshop.stub():
            api.emit("application.launched")

        # Wait for application launch to show Workfiles.
        if os.environ.get("AVALON_PHOTOSHOP_WORKFILES_ON_LAUNCH", True):
            if os.getenv("WORKFILES_SAVE_AS"):
                workfiles.show(save=False)
            else:
                workfiles.show()

    except ConnectionNotEstablishedYet:
        pass


@contextlib.contextmanager
def maintained_selection():
    """Maintain selection during context."""
    selection = stub().get_selected_layers()
    try:
        yield selection
    finally:
        stub().select_layers(selection)


@contextlib.contextmanager
def maintained_visibility():
    """Maintain visibility during context."""
    visibility = {}
    layers = stub().get_layers()
    for layer in layers:
        visibility[layer.id] = layer.visible
    try:
        yield
    finally:
        for layer in layers:
            stub().set_visible(layer.id, visibility[layer.id])
            pass
