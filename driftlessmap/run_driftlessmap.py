import sys

from .version import __version__


def run():
    if any(argument in {"--version", "-V"} for argument in sys.argv[1:]):
        print(__version__)
        return 0

    from .app import main

    return main()
