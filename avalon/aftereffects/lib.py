import os
import sys
import contextlib
import subprocess
import traceback
import logging
import functools
import asyncio

from wsrpc_aiohttp import (
    WebSocketRoute,
    WebSocketAsync
)

from Qt import QtWidgets

from avalon import api
from avalon.tools.webserver.app import WebServerTool

from openpype.tools.tray_app.app import ConsoleTrayApp
from openpype.tools.utils import host_tools

from openpype.lib.remote_publish import headless_publish

from .ws_stub import AfterEffectsServerStub

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def show(tool_name):
    """Call show on "module_name".

    This allows to make a QApplication ahead of time and always "exec_" to
    prevent crashing.

    Args:
        module_name (str): Name of module to call "show" on.
    """
    kwargs = {}
    if tool_name == "loader":
        kwargs["use_context"] = True

    host_tools.show_tool_by_name(tool_name, **kwargs)


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
    async def set_context(self, project, asset, task):
        """
            Sets 'project' and 'asset' to envs, eg. setting context

            Args:
                project (str)
                asset (str)
        """
        log.info("Setting context change")
        log.info("project {} asset {} ".format(project, asset))
        if project:
            api.Session["AVALON_PROJECT"] = project
            os.environ["AVALON_PROJECT"] = project
        if asset:
            api.Session["AVALON_ASSET"] = asset
            os.environ["AVALON_ASSET"] = asset
        if task:
            api.Session["AVALON_TASK"] = task
            os.environ["AVALON_TASK"] = task

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

    async def experimental_tools_route(self):
        self._tool_route("experimental_tools")

    def _tool_route(self, tool_name):
        """The address accessed when clicking on the buttons."""
        partial_method = functools.partial(show, tool_name)

        ConsoleTrayApp.execute_in_main_thread(partial_method)

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


def main(*subprocess_args):
    from avalon import aftereffects

    def is_host_connected():
        """Returns True if connected, False if app is not running at all."""
        if ConsoleTrayApp.process.poll() is not None:
            return False
        try:
            _stub = aftereffects.stub()

            if _stub:
                return True
        except Exception:
            pass

        return None

    # coloring in ConsoleTrayApp
    os.environ["OPENPYPE_LOG_NO_COLORS"] = "False"
    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)

    ConsoleTrayApp('aftereffects', launch, subprocess_args, is_host_connected)

    sys.exit(app.exec_())


def launch(*subprocess_args):
    """Starts the websocket server that will be hosted
       in the AfterEffects extension.
    """
    from avalon import api, aftereffects

    api.install(aftereffects)
    sys.excepthook = safe_excepthook

    # Launch aftereffects and the websocket server.
    ConsoleTrayApp.process = subprocess.Popen(
        subprocess_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    websocket_server = WebServerTool()
    route_name = 'AfterEffects'
    if websocket_server.port_occupied(websocket_server.host_name,
                                      websocket_server.port):
        log.info("Server already running, sending actual context and exit")
        asyncio.run(websocket_server.send_context_change(route_name))
        sys.exit(1)

    # Add Websocket route
    websocket_server.add_route("*", "/ws/", WebSocketAsync)
    # Add after effects route to websocket handler

    print("Adding {} route".format(route_name))
    WebSocketAsync.add_route(
        route_name, AfterEffectsRoute
    )
    websocket_server.start_server()

    ConsoleTrayApp.websocket_server = websocket_server

    if os.environ.get("HEADLESS_PUBLISH"):
        # reusing ConsoleTrayApp approach as it was already implemented
        ConsoleTrayApp.execute_in_main_thread(lambda: headless_publish(
            log,
            "CloseAE",
            os.environ.get("IS_TEST")))
        return

    if os.environ.get("AVALON_AFTEREFFECTS_WORKFILES_ON_LAUNCH", True):
        save = False
        if os.getenv("WORKFILES_SAVE_AS"):
            save = True

        ConsoleTrayApp.execute_in_main_thread(
            lambda: host_tools.show_tool_by_name("workfiles", save=save)
        )


@contextlib.contextmanager
def maintained_selection():
    """Maintain selection during context."""
    selection = stub().get_selected_items(True, False, False)
    try:
        yield selection
    finally:
        pass
