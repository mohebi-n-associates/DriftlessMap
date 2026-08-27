"""Run the test suite without invoking unstable Qt teardown at interpreter exit."""

import os
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def run_unittest():
    suite = unittest.defaultTestLoader.discover(
        str(Path(__file__).resolve().parent), pattern="test_*.py"
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def run_pytest():
    import pytest

    return int(pytest.main(["-q"]))


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"unittest", "pytest"}:
        print("usage: run_test_suite.py {unittest|pytest}", file=sys.stderr)
        return 2
    return run_unittest() if sys.argv[1] == "unittest" else run_pytest()


if __name__ == "__main__":
    exit_status = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # PyQt6/QOpenGLWidget can crash while Python tears down native objects on
    # headless Linux after all tests have completed. Preserve the actual test
    # status while avoiding that unrelated destructor path.
    os._exit(exit_status)
