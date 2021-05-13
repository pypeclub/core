import os
import sys
import contextlib
import subprocess
import queue
import importlib
import time
import traceback
import logging
import functools
import asyncio

from wsrpc_aiohttp import (
    WebSocketRoute,
    WebSocketAsync
)

from ..vendor.Qt import QtWidgets
from openpype.tools import workfiles
from avalon.tools.webserver.app import WebServerTool
from .ws_stub import AfterEffectsServerStub

self = sys.modules[__name__]
self.callback_queue = None

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def execute_in_main_thread(func_to_call_from_main_thread):
    if not self.callback_queue:  # safety
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
    if module_name == "workfiles":
        # Use OpenPype's workfiles tool
        tool_module = workfiles
    else:
        tool_module = importlib.import_module("avalon.tools." + module_name)

    if "loader" in module_name:
        tool_module.show(use_context=True)
    else:
        tool_module.show()

    # QApplication needs to always execute.
    app.exec_()


class ConnectionNotEstablishedYet(Exception):
    pass


class AfterEffectsRoute(WebSocketRoute):
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
        log.debug("someone called AfterEffects route")
        self.instance = self
        return kwargs

    # server functions
    async def ping(self):
        log.debug("someone called AfterEffects route ping")

    # This method calls function on the client side
    # client functions
    async def set_context(self, project, asset):
        """
            Sets 'project' and 'asset' to envs, eg. setting context

            Args:
                project (str)
                asset (str)
        """
        log.info("Setting context change")
        log.info("project {} asset {} ".format(project, asset))
        if project:
            os.environ["AVALON_PROJECT"] = project
        if asset:
            os.environ["AVALON_ASSET"] = asset

    async def read(self):
        log.debug("aftereffects.read client calls server server calls "
                  "aftereffects client")
        return await self.socket.call('aftereffects.read')

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

        execute_in_main_thread(partial_method)

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
    stub = AfterEffectsServerStub()
    if not stub.client:
        raise ConnectionNotEstablishedYet("Connection is not created yet")

    return stub


def safe_excepthook(*args):
    traceback.print_exception(*args)


def launch(*subprocess_args):
    """Starts the websocket server that will be hosted
       in the Photoshop extension.
    """
    from avalon import api, aftereffects

    api.install(aftereffects)
    sys.excepthook = safe_excepthook

    # Launch aftereffects and the websocket server.
    process = subprocess.Popen(subprocess_args, stdout=subprocess.PIPE)

    websocket_server = WebServerTool()

    if websocket_server.port_occupied(websocket_server.host_name,
                                      websocket_server.port):
        log.info("Server already running, sending actual context and exit")
        asyncio.run(websocket_server.send_context_change())
        sys.exit(1)

    # Add Websocket route
    websocket_server.add_route("*", "/ws/", WebSocketAsync)
    # Add after effects route to websocket handler
    route_name = 'AfterEffects'
    print("Adding {} route".format(route_name))
    WebSocketAsync.add_route(
        route_name, AfterEffectsRoute
    )
    websocket_server.start_server()

    while True:
        if process.poll() is not None:
            print("AfterEffects process is not alive. Exiting")
            websocket_server.stop()
            sys.exit(1)
        try:
            _stub = aftereffects.stub()
            if _stub:
                break
        except Exception:
            time.sleep(0.5)

    if os.environ.get("AVALON_AFTEREFFECTS_WORKFILES_ON_LAUNCH", True):
        if os.getenv("WORKFILES_SAVE_AS"):
            workfiles.show(save=False)
        else:
            workfiles.show()

    # AE could be closed immediately, withou workfile selection
    try:
        if aftereffects.stub():
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
    selection = stub().get_selected_items(True, False, False)
    try:
        yield selection
    finally:
        pass
