from ....vendor.Qt import QtCore, QtWidgets
from . import DeselectableTreeView


class AssetsView(DeselectableTreeView):
    """Item view.

    This implements a context menu.

    """

    def __init__(self):
        super(AssetsView, self).__init__()
        self.setIndentation(15)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.setHeaderHidden(True)

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            if modifiers == QtCore.Qt.ShiftModifier:
                return
            elif modifiers == QtCore.Qt.ControlModifier:
                return

        super(AssetsView, self).mousePressEvent(event)
