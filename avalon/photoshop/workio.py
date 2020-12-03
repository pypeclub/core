"""Host API required Work Files tool"""
import os

from . import lib
from avalon import api


def _active_document():
    document_name = lib.stub().get_active_document_name()
    if not document_name:
        return None

    return document_name


def file_extensions():
    return api.HOST_WORKFILE_EXTENSIONS["photoshop"]


def has_unsaved_changes():
    if _active_document():
        return not lib.stub().is_saved()

    return False


def save_file(filepath):
    lib.stub().saveAs(filepath, 'psd', True)


def open_file(filepath):
    lib.stub().open(filepath)

    return True


def current_file():
    try:
        return os.path.normpath(lib.stub().get_active_document_full_name()).\
                                replace("\\", "/")
    except Exception:
        return None


def work_root(session):
    return os.path.normpath(session["AVALON_WORKDIR"]).replace("\\", "/")
