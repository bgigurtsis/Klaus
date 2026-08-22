#!/bin/bash

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This installer requires macOS." >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd "$script_dir/.." && pwd)"
app_parent="${1:-$HOME/Applications}"
app_path="$app_parent/Klaus.app"
staging_path="$app_parent/.Klaus.app.tmp.$$"

cleanup() {
    rm -rf "$staging_path"
}
trap cleanup EXIT

if [[ ! -x "$source_root/.venv/bin/klaus" ]]; then
    echo "Klaus is not installed in $source_root/.venv." >&2
    echo "Create the environment before installing the app." >&2
    exit 1
fi

mkdir -p "$app_parent"
mkdir -p "$staging_path/Contents/MacOS" "$staging_path/Contents/Resources"

install -m 644 "$source_root/packaging/macos/Info.plist" "$staging_path/Contents/Info.plist"
xcrun clang -Os -Wall -Wextra -Werror -mmacosx-version-min=12.0 \
    "$source_root/packaging/macos/launcher.c" \
    -o "$staging_path/Contents/MacOS/Klaus"
printf '%s\n' "$source_root" >"$staging_path/Contents/Resources/source-root"
printf 'APPL????' >"$staging_path/Contents/PkgInfo"

"$source_root/.venv/bin/python" -c \
    'from PIL import Image; import sys; Image.open(sys.argv[1]).save(sys.argv[2], format="ICNS")' \
    "$source_root/klaus/ui/icon.png" \
    "$staging_path/Contents/Resources/Klaus.icns"

plutil -lint "$staging_path/Contents/Info.plist" >/dev/null
codesign --force --deep --sign - "$staging_path"

rm -rf "$app_path"
mv "$staging_path" "$app_path"
touch "$app_path"

launch_services="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$launch_services" ]]; then
    "$launch_services" -f "$app_path"
fi

echo "Installed Klaus at $app_path"
echo "Open it from Finder, Spotlight, or with: open \"$app_path\""
