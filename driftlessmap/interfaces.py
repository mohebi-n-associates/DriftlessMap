"""Choosing between the classic interface and the 2.0 preview.

Both interfaces ship in the same package and desktop bundle. The 2.0
interface starts by default (since 2.0.0a27); ``--classic`` on the command
line, or ``DRIFTLESSMAP_INTERFACE=classic`` in the environment, starts the
classic one. ``--v2`` / ``--preview`` and ``DRIFTLESSMAP_INTERFACE=v2`` still
select the 2.0 interface, and a flag wins over the environment. Each
interface can open the other in a separate process, so their windows,
preferences and OpenGL contexts stay independent.
"""

import os
import sys

PREVIEW_FLAGS = ("--v2", "--preview")
PREVIEW_NAMES = ("v2", "preview")
CLASSIC_FLAGS = ("--classic",)
CLASSIC_NAMES = ("classic",)


def requested_interface(argv=None, environ=None):
    """Return "preview" or "classic" for this launch."""
    argv = list(sys.argv if argv is None else argv)
    environ = os.environ if environ is None else environ
    arguments = argv[1:]
    if any(argument in CLASSIC_FLAGS for argument in arguments):
        return "classic"
    if any(argument in PREVIEW_FLAGS for argument in arguments):
        return "preview"
    if environ.get("DRIFTLESSMAP_INTERFACE", "").strip().lower() in CLASSIC_NAMES:
        return "classic"
    return "preview"


def without_interface_flags(argv):
    return [argument for argument in argv
            if argument not in PREVIEW_FLAGS + CLASSIC_FLAGS]


def interface_command(interface, frozen=None, executable=None):
    """The program and arguments that start ``interface`` in a new process.

    A desktop bundle (frozen) restarts its own executable; a Python install
    runs the package with the current interpreter.
    """
    if interface not in ("classic", "preview"):
        raise ValueError("Unknown interface {!r}.".format(interface))
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = sys.executable if executable is None else executable
    if frozen:
        return executable, (["--v2"] if interface == "preview" else ["--classic"])
    if interface == "preview":
        return executable, ["-m", "driftlessmap.v2"]
    return executable, ["-m", "driftlessmap", "--classic"]


def start_interface(interface):
    """Start ``interface`` in a new process; return whether it started."""
    from PyQt6.QtCore import QProcess, QProcessEnvironment

    program, arguments = interface_command(interface)
    environment = dict(os.environ)
    environment.pop("DRIFTLESSMAP_INTERFACE", None)
    process = QProcess()
    process.setProgram(program)
    process.setArguments(arguments)
    qt_environment = QProcessEnvironment()
    for key, value in environment.items():
        qt_environment.insert(key, value)
    process.setProcessEnvironment(qt_environment)
    started, _pid = process.startDetached()
    return bool(started)
