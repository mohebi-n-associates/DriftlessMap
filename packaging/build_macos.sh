#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"

# Exact versions keep release bundles reproducible.
python -m pip install --upgrade \
  --constraint packaging/constraints-desktop.txt ".[czi,desktop-build]"
python -m PyInstaller --noconfirm --clean packaging/DriftlessMap.spec

version="$(python -c 'from driftlessmap.version import __version__; print(__version__)')"
artifact="dist/DriftlessMap-${version}-macOS-arm64.dmg"
work_dir="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"

signing=false
if [[ -n "${MACOS_CERTIFICATE_P12_BASE64:-}" && -n "${MACOS_SIGNING_IDENTITY:-}" ]]; then
  signing=true
  keychain="${work_dir}/driftlessmap-build.keychain-db"
  keychain_password="$(uuidgen)"
  echo "${MACOS_CERTIFICATE_P12_BASE64}" | base64 --decode > "${work_dir}/signing.p12"
  security create-keychain -p "${keychain_password}" "${keychain}"
  security set-keychain-settings -lut 21600 "${keychain}"
  security unlock-keychain -p "${keychain_password}" "${keychain}"
  security import "${work_dir}/signing.p12" -P "${MACOS_CERTIFICATE_PASSWORD:-}" \
    -A -t cert -f pkcs12 -k "${keychain}"
  rm -f "${work_dir}/signing.p12"
  security list-keychains -d user -s "${keychain}" \
    $(security list-keychains -d user | tr -d '"')
  security set-key-partition-list -S apple-tool:,apple: -s \
    -k "${keychain_password}" "${keychain}" > /dev/null
  codesign --force --deep --options runtime --timestamp \
    --sign "${MACOS_SIGNING_IDENTITY}" dist/DriftlessMap.app
fi

hdiutil create -volname DriftlessMap -srcfolder dist/DriftlessMap.app \
  -ov -format UDZO "$artifact"

if [[ "${signing}" == true ]]; then
  codesign --force --timestamp --sign "${MACOS_SIGNING_IDENTITY}" "$artifact"
  if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" ]]; then
    xcrun notarytool submit "$artifact" --apple-id "${APPLE_ID}" \
      --team-id "${APPLE_TEAM_ID}" --password "${APPLE_APP_PASSWORD}" --wait
    xcrun stapler staple "$artifact"
  fi
else
  echo "Signing secrets are not configured; the DMG is unsigned."
fi
echo "Created $artifact"
