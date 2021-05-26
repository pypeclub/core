import collections
import sys
import contextlib
import subprocess
import queue
import importlib
import logging
import functools
import time
import traceback
from io import StringIO

from wsrpc_aiohttp import (
    WebSocketRoute,
    WebSocketAsync
)

from Qt import QtWidgets, QtCore, QtGui

from avalon import style
from avalon.tools.webserver.app import WebServerTool

from openpype.tools import workfiles
from openpype import resources

from .ws_stub import PhotoshopServerStub

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def execute_in_main_thread(func_to_call_from_main_thread):
    if not TrayApp.callback_queue:
        TrayApp.callback_queue = queue.Queue()
    TrayApp.callback_queue.put(func_to_call_from_main_thread)


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
    stub = PhotoshopServerStub()
    if not stub.client:
        raise ConnectionNotEstablishedYet("Connection is not created yet")

    return stub


def safe_excepthook(*args):
    traceback.print_exception(*args)


class TrayApp:
    callback_queue = None

    def __init__(self, host):
        self.host = host

        self.initialized = False
        self.websocket_server = None
        self.timer = None
        self.subprocess_args = None
        self.initializing = False
        self.tray = False

        self.original_stdout_write = None
        self.original_stderr_write = None
        self.new_text = collections.deque()

        self.icons = self._select_icons(self.host)
        self.status_texts = self._prepare_status_texts(self.host)

        tray = QtWidgets.QSystemTrayIcon()

        tray.show()
        tray.activated.connect(self.open_console)

        self.tray = tray
        self.dialog = ConsoleDialog(self.new_text)

        self.change_status("initializing")

    def _prepare_status_texts(self, host_name):
        status_texts = {
            'initializing': "Starting communication with {}".format(self.host),
            'ready': "Communicating with {}".format(self.host),
            'error': "Error!"
        }

        return status_texts

    def _select_icons(self, host_name):
        # use host_name
        icons = {
            'initializing': QtGui.QIcon(
                resources.get_resource("icons", "circle_orange.png")
            ),
            'ready': QtGui.QIcon(
                resources.get_resource("icons", "circle_green.png")
            ),
            'error': QtGui.QIcon(
                resources.get_resource("icons", "circle_red.png")
            )
        }

        return icons

    def on_timer(self):
        self.dialog.append_text(self.new_text)
        if not self.initialized:
            if self.initializing:
                return
            TrayApp.callback_queue = queue.Queue()
            self.initializing = True

            launch(*self.subprocess_args)
            self.initialized = True
            self.initializing = False
            self.change_status("ready")
        elif TrayApp.callback_queue:
            try:
                callback = TrayApp.callback_queue.get(block=False)
                callback()
            except queue.Empty:
                pass
        else:
            if self.process.poll() is not None:
                # Wait on Photoshop to close before closing the websocket serv.
                self.process.wait()
                self.websocket_server.stop()
                self.timer.stop()
                self.change_status("error")

    def redirect_stds(self):
        if sys.stdout:
            self.original_stdout_write = sys.stdout.write
        else:
            sys.stdout = StringIO()

        if sys.stderr:
            self.original_stderr_write = sys.stdout.write
        else:
            sys.stderr = StringIO()

        sys.stdout.write = self.my_stdout_write
        sys.stderr.write = self.my_stderr_write

    def my_stdout_write(self, text):
        if self.original_stdout_write is not None:
            self.original_stdout_write(text)
        self.new_text.append(text)

    def my_stderr_write(self, text):
        if self.original_stderr_write is not None:
            self.original_stderr_write(text)
        self.new_text.append(text)

    def change_status(self, status):
        self._change_tooltip(status)
        self._change_icon(status)

    def _change_tooltip(self, status):
        status = self.status_texts.get(status)
        if not status:
            raise ValueError("Unknown state")

        self.tray.setToolTip(status)

    def _change_icon(self, state):
        icon = self.icons.get(state)
        if not icon:
            raise ValueError("Unknown state")

        self.tray.setIcon(icon)

    def open_console(self):
        self.dialog.show()


class ConsoleDialog(QtWidgets.QDialog):
    WIDTH = 720
    HEIGHT = 450

    def __init__(self, text, parent=None):
        super(ConsoleDialog, self).__init__(parent)
        layout = QtWidgets.QHBoxLayout(parent)

        plain_text = QtWidgets.QPlainTextEdit(self)
        plain_text.setReadOnly(True)
        plain_text.resize(self.WIDTH, self.HEIGHT)
        while text:
            plain_text.appendPlainText(text.popleft().strip())

        layout.addWidget(plain_text)

        self.plain_text = plain_text

        self.setStyleSheet(style.load_stylesheet())

        self.resize(self.WIDTH, self.HEIGHT)

    def append_text(self, new_text):
        while new_text:
            self.plain_text.appendPlainText(new_text.popleft().rstrip())

def main(*subprocess_args):
    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)

    trayApp = TrayApp('photoshop')
    trayApp.redirect_stds()
    trayApp.subprocess_args = subprocess_args

    timer = QtCore.QTimer()
    trayApp.timer = timer
    timer.timeout.connect(trayApp.on_timer)
    timer.setInterval(200)
    timer.start()

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
        # if os.environ.get("AVALON_PHOTOSHOP_WORKFILES_ON_LAUNCH", True):
        #     if os.getenv("WORKFILES_SAVE_AS"):
        #         workfiles.show(save=False)
        #     else:
        #         workfiles.show()

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
