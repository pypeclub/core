import contextlib
import subprocess
import os
import sys
import queue
import importlib
import time
import traceback

from ..vendor.Qt import QtWidgets
from ..tools import workfiles

from pype.modules.websocket_server import WebSocketServer
from pype.modules.websocket_server.stubs.photoshop_server_stub import (
    PhotoshopServerStub
)

self = sys.modules[__name__]
self.callback_queue = None


def execute_in_main_thread(func_to_call_from_main_thread):
    if not self.callback_queue:
        self.callback_queue = queue.Queue()
    self.callback_queue.put(func_to_call_from_main_thread)


def main_thread_listen(process, websocket_server):
    if process.poll() is not None:  # check if PS still running
        websocket_server.stop()
        sys.exit(1)
    try:
        # get is blocking, wait for 2sec to give poll() chance to close
        callback = self.callback_queue.get(True, 2)
        callback()
    except queue.Empty:
        pass


def show(module_name):
    """Call show on "module_name".

    This allows to make a QApplication ahead of time and always "exec_" to
    prevent crashing.

    Args:
        module_name (str): Name of module to call "show" on.
    """
    # Need to have an existing QApplication.
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    # Import and show tool.
    tool_module = importlib.import_module("avalon.tools." + module_name)

    if "loader" in module_name:
        tool_module.show(use_context=True)
    else:
        tool_module.show()

    # QApplication needs to always execute.
    app.exec_()


class ConnectionNotEstablishedYet(Exception):
    pass


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


def launch(application):
    """Starts the websocket server that will be hosted
       in the Photoshop extension.
    """
    from avalon import api, photoshop

    api.install(photoshop)
    sys.excepthook = safe_excepthook
    # Launch Photoshop and the websocket server.
    process = subprocess.Popen(application, stdout=subprocess.PIPE)

    websocket_server = WebSocketServer()
    websocket_server.websocket_thread.start()

    while True:
        if process.poll() is not None:
            print("Photoshop process is not alive. Exiting")
            websocket_server.stop()
            sys.exit(1)
        try:
            _stub = photoshop.stub()
            if _stub:
                break
        except Exception:
            time.sleep(0.5)

    # Wait for application launch to show Workfiles.
    if os.environ.get("AVALON_PHOTOSHOP_WORKFILES_ON_LAUNCH", True):
        if os.getenv("WORKFILES_SAVE_AS"):
            workfiles.show(save=False)
        else:
            workfiles.show()

    # Photoshop could be closed immediately, withou workfile selection
    try:
        if photoshop.stub():
            api.emit("application.launched")

        self.callback_queue = queue.Queue()
        while True:
            main_thread_listen(process, websocket_server)

    except ConnectionNotEstablishedYet:
        pass
    finally:
        # Wait on Photoshop to close before closing the websocket server
        process.wait()
        websocket_server.stop()


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

