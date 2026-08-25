#!/bin/bash

set -euo pipefail

stream_version="v1.3.1-paperpure.4"
stream_sha512="c6dd3e5167a5e3a98a7bc0688a1142d3c6a53f2de07e1350dbf1ca31803dd7182eabc38ea48f7e543bd804cd92f0a8fb2d5ddb13c60ea7d08bb12ff4f93238e8"
default_host="root@10.11.99.1"
default_address="https://10.11.99.1:2001"

usage() {
    cat <<'EOF'
Install and pair Klaus with a reMarkable Paper Pure.

Usage:
  ./scripts/install-remarkable-paperpure.sh [options]

Options:
  --host USER@HOST       SSH destination (default: root@10.11.99.1)
  --address URL          Screenshot service URL (default: https://10.11.99.1:2001)
  --socket PATH          Klaus pairing socket (default: ~/.klaus/remanager-pairing.sock)
  -h, --help             Show this help

The installer asks SSH for the tablet password. It never accepts that password
as a command-line option. Open Klaus before running the installer.
EOF
}

tablet_host="$default_host"
tablet_address="$default_address"
pairing_socket="${KLAUS_DATA_DIR:-$HOME/.klaus}/remanager-pairing.sock"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            [[ $# -ge 2 ]] || { echo "--host needs a value." >&2; exit 2; }
            tablet_host="$2"
            shift 2
            ;;
        --address)
            [[ $# -ge 2 ]] || { echo "--address needs a value." >&2; exit 2; }
            tablet_address="$2"
            shift 2
            ;;
        --socket)
            [[ $# -ge 2 ]] || { echo "--socket needs a value." >&2; exit 2; }
            pairing_socket="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

for command_name in curl python3 shasum ssh tar; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "Missing required command: $command_name" >&2
        exit 1
    }
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd "$script_dir/.." && pwd)"
payload_source="$source_root/packaging/remarkable"
pairing_client="$script_dir/pair-remarkable.py"

for required_file in \
    "$payload_source/install-tablet.sh" \
    "$payload_source/klaus-remarkable-prepare" \
    "$payload_source/klaus-remarkable.service" \
    "$pairing_client"; do
    if [[ ! -f "$required_file" ]]; then
        echo "The installer is incomplete. Clone the Klaus repository and run it there." >&2
        exit 1
    fi
done

if ! python3 "$pairing_client" --check --socket "$pairing_socket"; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
        open -a Klaus >/dev/null 2>&1 || true
        for _ in {1..10}; do
            sleep 1
            if python3 "$pairing_client" --check --socket "$pairing_socket"; then
                break
            fi
        done
    fi
fi

if ! python3 "$pairing_client" --check --socket "$pairing_socket"; then
    echo "Open Klaus, then run this installer again." >&2
    exit 1
fi

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/klaus-paper-pure.XXXXXX")"
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT

cp "$payload_source/install-tablet.sh" "$work_dir/"
cp "$payload_source/klaus-remarkable-prepare" "$work_dir/"
cp "$payload_source/klaus-remarkable.service" "$work_dir/"

stream_url="https://github.com/bgigurtsis/goMarkableStream/releases/download/$stream_version/goMarkableStream-PaperPure"
echo "Downloading the Paper Pure screenshot service..."
curl --fail --location --silent --show-error "$stream_url" \
    --output "$work_dir/goMarkableStream"

actual_sha512="$(shasum -a 512 "$work_dir/goMarkableStream" | awk '{print $1}')"
if [[ "$actual_sha512" != "$stream_sha512" ]]; then
    echo "The screenshot service checksum does not match." >&2
    exit 1
fi
chmod 755 "$work_dir/goMarkableStream"

echo "Connecting to $tablet_host. Enter the tablet SSH password when asked."
set +e
pairing_payload="$(tar -C "$work_dir" -cf - . | ssh "$tablet_host" '
    set -eu
    remote_dir=$(mktemp -d /tmp/klaus-paper-pure.XXXXXX)
    cleanup() { rm -rf "$remote_dir"; }
    trap cleanup EXIT
    tar -xf - -C "$remote_dir"
    sh "$remote_dir/install-tablet.sh" "$remote_dir"
')"
install_status=$?
set -e

if [[ $install_status -ne 0 ]]; then
    echo "Paper Pure installation failed." >&2
    exit "$install_status"
fi

printf '%s\n' "$pairing_payload" \
    | python3 "$pairing_client" \
        --socket "$pairing_socket" \
        --address "$tablet_address"

echo "Paper Pure is installed and paired. Future updates can use this same command."
