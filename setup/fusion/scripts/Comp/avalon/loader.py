import avalon.api
import avalon.fusion
from openpype.tools.utils import host_tools


avalon.api.install(avalon.fusion)
host_tools.show_loader(use_context=True)
