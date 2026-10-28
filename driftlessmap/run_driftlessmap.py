import sys

from .interfaces import PREVIEW_FLAGS, requested_interface, without_interface_flags
from .version import __version__


def run():
    arguments = sys.argv[1:]
    # A plain --version prints only the version, whichever interface is the default.
    if (any(argument in {"--version", "-V"} for argument in arguments)
            and not any(argument in PREVIEW_FLAGS for argument in arguments)):
        print(__version__)
        return 0
    if requested_interface() == "preview":
        from .v2 import main as preview_main

        return preview_main(without_interface_flags(sys.argv))

    from .app import main

    sys.argv = without_interface_flags(sys.argv)
    return main()
