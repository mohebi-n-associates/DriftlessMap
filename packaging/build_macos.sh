#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

python -m pip install --upgrade ".[czi,desktop-build]"
python -m PyInstaller --noconfirm --clean packaging/DriftlessMap.spec

version="$(python -c 'from driftlessmap.version import __version__; print(__version__)')"
artifact="dist/DriftlessMap-${version}-macOS.dmg"
hdiutil create -volname DriftlessMap -srcfolder dist/DriftlessMap.app \
  -ov -format UDZO "$artifact"
echo "Created $artifact"
