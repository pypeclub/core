from openpype.lib.build_template import build_workfile_template


def show(root=None, debug=False, parent=None, use_context=True, save=True):
    """Proxy function used to trick photoshop menu to build a scene"""
    build_workfile_template()