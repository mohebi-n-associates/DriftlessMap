## Work on DriftlessMap in PyCharm

This is for developers who want to run DriftlessMap from its source code.
To use DriftlessMap, the desktop builds on the
[Releases page](https://github.com/mohebi-n-associates/DriftlessMap/releases)
or `pip install driftlessmap` are simpler (see the
[User Manual, Section 2](../MANUAL.md#2-installation-and-launching)).

DriftlessMap supports Python 3.10-3.14. Use Python 3.14, or 3.13 if you need
Zeiss CZI files.

1. Install [PyCharm](https://www.jetbrains.com/pycharm/).
2. Clone the repository, either with **File > Project from Version Control**
   and the URL `https://github.com/mohebi-n-associates/DriftlessMap.git`, or in
   a terminal:

   ```bash
   git clone https://github.com/mohebi-n-associates/DriftlessMap.git
   ```

3. Open the folder as a PyCharm project and give it a new interpreter
   (**Settings > Project > Python Interpreter > Add Interpreter**; a virtualenv
   or conda environment with Python 3.14). PyCharm's guide:
   [Configure a Python interpreter](https://www.jetbrains.com/help/pycharm/configuring-python-interpreter.html).
4. In PyCharm's terminal, install DriftlessMap from the source in editable
   mode, with the test tools:

   ```bash
   python -m pip install -e ".[test]"
   ```

   For CZI support (Python 3.13): `python -m pip install -e ".[test,czi]"`.
5. Run it with `python -m driftlessmap`, or create a *Run configuration* with
   module `driftlessmap`. Add `--classic` for the classic interface.
6. Run the tests:

   ```bash
   QT_API=pyqt6 QT_QPA_PLATFORM=offscreen python tests/run_test_suite.py unittest
   ```

   On Windows, set the two variables in PowerShell first
   (`$env:QT_API="pyqt6"; $env:QT_QPA_PLATFORM="offscreen"`).
