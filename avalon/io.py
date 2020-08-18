"""Wrapper around interactions with the database"""

import os
import sys
import errno
import shutil
import logging
import tempfile
import contextlib

from .vendor import requests

# Third-party dependencies
from bson.objectid import ObjectId, InvalidId

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
]

self = sys.modules[__name__]
self._mongo_client = None
self._sentry_client = None
self._sentry_logging_handler = None
self._database = None
self._is_installed = False

log = logging.getLogger(__name__)


def install():
    # TODO Global context
    pass


def uninstall():
    # TODO Global context
    pass


def active_project():
    # TODO Global context
    pass


def projects():
    # TODO Global context
    pass


def locate(path):
    # TODO Global context
    pass


def insert_one(item):
    # TODO Global context
    pass


def insert_many(items, ordered=True):
    # TODO Global context
    pass


def find(filter, projection=None, sort=None):
    # TODO Global context
    pass


def find_one(filter, projection=None, sort=None):
    # TODO Global context
    pass


def save(*args, **kwargs):
    # TODO Global context
    pass


def replace_one(filter, replacement):
    # TODO Global context
    pass


def update_many(filter, update):
    # TODO Global context
    pass


def distinct(*args, **kwargs):
    # TODO Global context
    pass


def aggregate(*args, **kwargs):
    # TODO Global context
    pass


def drop(*args, **kwargs):
    # TODO Global context
    pass


def delete_many(*args, **kwargs):
    # TODO Global context
    pass


def parenthood(document):
    # TODO Global context
    pass


@contextlib.contextmanager
def tempdir():
    tempdir = tempfile.mkdtemp()
    try:
        yield tempdir
    finally:
        shutil.rmtree(tempdir)


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
