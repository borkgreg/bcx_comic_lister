#!/usr/bin/env bash
set -euo pipefail

# Requires: brew install create-dmg

APP_NAME="BCX Comic Lister"
APP_PATH="dist/${APP_NAME}.app"
OUT_DMG="dist/${APP_NAME}.dmg"

if [[ ! -d "$APP_PATH" ]]; then
  echo "Missing app at: $APP_PATH"
  echo "Build first with: pyinstaller bcx_master_app.spec --noconfirm --clean"
  exit 1
fi

rm -f "$OUT_DMG"

create-dmg \
  --volname "$APP_NAME" \
  --window-size 540 360 \
  --icon-size 96 \
  --app-drop-link 390 185 \
  "$OUT_DMG" \
  "$APP_PATH"
