import sys

from .interfaces import requested_interface, without_interface_flags
from .version import __version__


def run():
    if requested_interface() == "preview":
        from .v2 import main as preview_main

        return preview_main(without_interface_flags(sys.argv))
    if any(argument in {"--version", "-V"} for argument in sys.argv[1:]):
        print(__version__)
        return 0

    from .app import main

    return main()
