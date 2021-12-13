import os
import sys
import contextlib
import traceback
import logging

from wsrpc_aiohttp import (
    WebSocketRoute,
    WebSocketAsync
)

from Qt import QtWidgets

from openpype.tools.utils import host_tools
from .launch_logic import ProcessLauncher, stub


log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def safe_excepthook(*args):
    traceback.print_exception(*args)


def main(*subprocess_args):
    sys.excepthook = safe_excepthook

    from avalon import api, aftereffects

    api.install(aftereffects)

    os.environ["OPENPYPE_LOG_NO_COLORS"] = "False"
    app = QtWidgets.QApplication([])
    app.setQuitOnLastWindowClosed(False)

    launcher = ProcessLauncher(subprocess_args)
    launcher.start()

    # Launch aftereffects and the websocket server.
    if os.environ.get("AVALON_PHOTOSHOP_WORKFILES_ON_LAUNCH", True):
        save = False
        if os.getenv("WORKFILES_SAVE_AS"):
            save = True

        launcher.execute_in_main_thread(
            lambda: host_tools.show_tool_by_name("workfiles", save=save)
        )

    sys.exit(app.exec_())


@contextlib.contextmanager
def maintained_selection():
    """Maintain selection during context."""
    selection = stub().get_selected_items(True, False, False)
    try:
        yield selection
    finally:
        pass
