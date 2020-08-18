"""Wrapper around interactions with the database"""

import os
import errno
import shutil
import logging
import tempfile
import contextlib
import functools

from .vendor import requests

# Third-party dependencies
from bson.objectid import ObjectId, InvalidId

GLOBAL_CONTEXT = None
Session = None

__all__ = [
    "ObjectId",
    "InvalidId",
    "install",
    "uninstall",
    "projects",
    "locate",
    "insert_one",
    "find",
    "find_one",
    "save",
    "replace_one",
    "update_many",
    "distinct",
    "drop",
    "delete_many",
    "parenthood",
    "database"
]

log = logging.getLogger(__name__)


def check_global_context(func):
    @functools.wraps(func)
    def decorated(*args, **kwargs):
        global GLOBAL_CONTEXT
        if GLOBAL_CONTEXT is None:
            global Session
            from . import GLOBAL_CONTEXT as _GLOBAL_CONTEXT
            from . import Session as _Session
            GLOBAL_CONTEXT = _GLOBAL_CONTEXT
            Session = _Session
        return func(*args, **kwargs)
    return decorated


@check_global_context
def database():
    return GLOBAL_CONTEXT.dbcon.database


@check_global_context
def install():
    return GLOBAL_CONTEXT.dbcon.install()


@check_global_context
def uninstall():
    return GLOBAL_CONTEXT.dbcon.uninstall()


@check_global_context
def active_project():
    return GLOBAL_CONTEXT.dbcon.active_project()


@check_global_context
def projects():
    return GLOBAL_CONTEXT.dbcon.projects()


@check_global_context
def locate(path):
    return GLOBAL_CONTEXT.dbcon.locate(path)


@check_global_context
def insert_one(item):
    return GLOBAL_CONTEXT.dbcon.insert_one(item)


@check_global_context
def insert_many(items, ordered=True):
    return GLOBAL_CONTEXT.dbcon.insert_many(items, ordered=True)


@check_global_context
def find(filter, projection=None, sort=None):
    return GLOBAL_CONTEXT.dbcon.find(filter, projection=None, sort=None)


@check_global_context
def find_one(filter, projection=None, sort=None):
    return GLOBAL_CONTEXT.dbcon.find_one(filter, projection=None, sort=None)


@check_global_context
def save(*args, **kwargs):
    return GLOBAL_CONTEXT.dbcon.save(*args, **kwargs)


@check_global_context
def replace_one(filter, replacement):
    return GLOBAL_CONTEXT.dbcon.replace_one(filter, replacement)


@check_global_context
def update_many(filter, update):
    return GLOBAL_CONTEXT.dbcon.update_many(filter, update)


@check_global_context
def distinct(*args, **kwargs):
    return GLOBAL_CONTEXT.dbcon.distinct(*args, **kwargs)


@check_global_context
def aggregate(*args, **kwargs):
    return GLOBAL_CONTEXT.dbcon.aggregate(*args, **kwargs)


@check_global_context
def drop(*args, **kwargs):
    return GLOBAL_CONTEXT.dbcon.drop(*args, **kwargs)


@check_global_context
def delete_many(*args, **kwargs):
    return GLOBAL_CONTEXT.dbcon.delete_many(*args, **kwargs)


@check_global_context
def parenthood(document):
    return GLOBAL_CONTEXT.dbcon.parenthood(document)


@contextlib.contextmanager
def tempdir():
    tempdir = tempfile.mkdtemp()
    try:
        yield tempdir
    finally:
        shutil.rmtree(tempdir)


@check_global_context
def download(src, dst):
    """Download `src` to `dst`

    Arguments:
        src (str): URL to source file
        dst (str): Absolute path to destination file

    Yields tuple (progress, error):
        progress (int): Between 0-100
        error (Exception): Any exception raised when first making connection

    """

    try:
        response = requests.get(
            src,
            stream=True,
            auth=requests.auth.HTTPBasicAuth(
                Session["AVALON_USERNAME"],
                Session["AVALON_PASSWORD"]
            )
        )
    except requests.ConnectionError as e:
        yield None, e
        return

    with tempdir() as dirname:
        tmp = os.path.join(dirname, os.path.basename(src))

        with open(tmp, "wb") as f:
            total_length = response.headers.get("content-length")

            if total_length is None:  # no content length header
                f.write(response.content)
            else:
                downloaded = 0
                total_length = int(total_length)
                for data in response.iter_content(chunk_size=4096):
                    downloaded += len(data)
                    f.write(data)

                    yield int(100.0 * downloaded / total_length), None

        try:
            os.makedirs(os.path.dirname(dst))
        except OSError as e:
            # An already existing destination directory is fine.
            if e.errno != errno.EEXIST:
                raise

        shutil.copy(tmp, dst)
