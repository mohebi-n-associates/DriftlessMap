"""File dialogs that start in the folder the user last worked in.

Every open, save and folder dialog goes through these functions. A dialog
that would start in the home folder (or nowhere) starts in the folder last
chosen in any dialog instead, remembered between sessions; a dialog that
starts somewhere specific, such as the current image's folder, keeps it.
"""

import os

from PyQt6.QtWidgets import QFileDialog

from . import user_settings

_last = {"folder": None, "loaded": False}


def last_folder():
    """The folder last chosen in a dialog, if it still exists."""
    if not _last["loaded"]:
        _last["loaded"] = True
        _last["folder"] = user_settings.load_last_folder()
    folder = _last["folder"]
    return folder if folder and os.path.isdir(folder) else None


def remember(path):
    """Remember the folder of a chosen file or folder."""
    if not path:
        return
    path = os.fspath(path)
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if not folder or not os.path.isdir(folder):
        return
    folder = os.path.abspath(folder)
    _last["loaded"] = True
    if folder == _last["folder"]:
        return
    _last["folder"] = folder
    try:
        user_settings.save_last_folder(folder)
    except OSError:
        pass  # remembered for this session only


def _is_home(folder):
    home = os.path.expanduser("~")
    return os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(home))


def start_in(directory):
    """Where a dialog asked to start at ``directory`` should start.

    ``directory`` may be a folder or a suggested file path. When it is empty,
    the home folder or a folder that no longer exists, the last used folder
    is used instead (keeping a suggested file name).
    """
    directory = os.fspath(directory) if directory else ""
    last = last_folder()
    if last is None:
        return directory
    if not directory:
        return last
    if os.path.isdir(directory):
        return last if _is_home(directory) else directory
    folder, name = os.path.split(directory)
    if not folder or _is_home(folder) or not os.path.isdir(folder):
        return os.path.join(last, name) if name else last
    return directory


def _directory_argument(args, kwargs):
    """Replace the ``directory`` argument (third positional or keyword)."""
    args = list(args)
    if len(args) >= 3:
        args[2] = start_in(args[2])
    else:
        while len(args) < 2:
            args.append(None if not args else "")
        if "directory" in kwargs:
            kwargs["directory"] = start_in(kwargs["directory"])
        else:
            args.append(start_in(""))
    return args, kwargs


def get_open_file_name(*args, **kwargs):
    args, kwargs = _directory_argument(args, kwargs)
    result = QFileDialog.getOpenFileName(*args, **kwargs)
    remember(result[0])
    return result


def get_open_file_names(*args, **kwargs):
    args, kwargs = _directory_argument(args, kwargs)
    result = QFileDialog.getOpenFileNames(*args, **kwargs)
    if result[0]:
        remember(result[0][0])
    return result


def get_save_file_name(*args, **kwargs):
    args, kwargs = _directory_argument(args, kwargs)
    result = QFileDialog.getSaveFileName(*args, **kwargs)
    remember(result[0])
    return result


def get_existing_directory(*args, **kwargs):
    args, kwargs = _directory_argument(args, kwargs)
    result = QFileDialog.getExistingDirectory(*args, **kwargs)
    remember(result)
    return result
