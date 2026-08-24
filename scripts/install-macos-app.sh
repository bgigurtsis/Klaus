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
staging_path="$app_parent/.Klaus.app.tmp.$$.app"
codesign_identity="${KLAUS_CODESIGN_IDENTITY:-}"

if [[ "$codesign_identity" == "-" ]]; then
    echo "KLAUS_CODESIGN_IDENTITY must name a certificate, not '-'." >&2
    exit 1
fi

if [[ -n "$codesign_identity" ]]; then
    signature_format="certificate-app-bundle-v1:$codesign_identity"
else
    signature_format="linker-executable-v1"
fi

cleanup() {
    rm -rf "$staging_path"
}
trap cleanup EXIT

if [[ ! -x "$source_root/.venv/bin/klaus" ]]; then
    echo "Klaus is not installed in $source_root/.venv." >&2
    echo "Create the environment before installing the app." >&2
    exit 1
fi

# Rebuilding the launcher can invalidate TCC grants (Screen Recording, mic).
# The installer should skip unchanged inputs to preserve existing grants.
build_stamp="$(cat \
    "$source_root/packaging/macos/launcher.c" \
    "$source_root/packaging/macos/Info.plist" \
    "$source_root/klaus/ui/icon.png" \
    <(printf '%s\n%s\n%s\n' \
        "$source_root" "$signature_format" "installer-signing-v3") \
    | shasum -a 256 | cut -d' ' -f1)"

signature_is_valid() {
    if [[ -n "$codesign_identity" ]]; then
        codesign --verify --deep --strict "$app_path" 2>/dev/null
    else
        codesign --verify --strict --ignore-resources \
            "$app_path/Contents/MacOS/Klaus" 2>/dev/null
    fi
}

stamp_file="$app_path/Contents/Resources/build-stamp"
if [[ -f "$stamp_file" ]] \
    && [[ "$(cat "$stamp_file")" == "$build_stamp" ]] \
    && signature_is_valid; then
    echo "Klaus.app is up to date at $app_path (skipped reinstall to keep"
    echo "Screen Recording and microphone permissions intact)."
    exit 0
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

printf '%s\n' "$build_stamp" >"$staging_path/Contents/Resources/build-stamp"

plutil -lint "$staging_path/Contents/Info.plist" >/dev/null
if [[ -n "$codesign_identity" ]]; then
    codesign --force --deep --sign "$codesign_identity" "$staging_path"
    codesign --verify --deep --strict "$staging_path"
else
    codesign --verify --strict --ignore-resources \
        "$staging_path/Contents/MacOS/Klaus"
fi

rm -rf "$app_path"
mv "$staging_path" "$app_path"
touch "$app_path"

launch_services="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$launch_services" ]]; then
    if ! "$launch_services" -f "$app_path"; then
        echo "Warning: Spotlight registration failed, but Klaus.app is installed." >&2
    fi
fi

echo "Installed Klaus at $app_path"
echo "Open it from Finder, Spotlight, or with: open \"$app_path\""
if [[ -n "$codesign_identity" ]]; then
    echo "Signed Klaus with identity: $codesign_identity"
fi
echo "If macOS asks again after a launcher change, renew Klaus's access under"
echo "System Settings > Privacy & Security."
