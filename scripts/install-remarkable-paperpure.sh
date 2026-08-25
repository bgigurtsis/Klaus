#!/bin/bash

set -euo pipefail

stream_version="v1.3.1-paperpure.4"
stream_sha512="c6dd3e5167a5e3a98a7bc0688a1142d3c6a53f2de07e1350dbf1ca31803dd7182eabc38ea48f7e543bd804cd92f0a8fb2d5ddb13c60ea7d08bb12ff4f93238e8"
tablet_installer_sha256="284f604b420ae8b5869243e53500845b57d2498ef8cf692c2d9f92487eefa655"
tablet_prepare_sha256="6a80c10fc3333185468b7f75c06aaa214ce2ca43db1a4b18543e6e6441136878"
tablet_service_sha256="ce146fce22b17eff35425300fcf76abeb7076e877555d538485b00b2cac338c4"
pairing_client_sha256="00e920d8ce39eb8883cd27ef82acc6a59955d22994578993234f8895bd22a793"
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

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This installer requires macOS." >&2
    exit 1
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_root="$(cd "$script_dir/.." && pwd)"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/klaus-paper-pure.XXXXXX")"
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT

verify_sha256() {
    local file_path="$1"
    local expected="$2"
    local actual
    actual="$(shasum -a 256 "$file_path" | awk '{print $1}')"
    if [[ "$actual" != "$expected" ]]; then
        echo "The checksum does not match for $(basename "$file_path")." >&2
        exit 1
    fi
}

prepare_asset() {
    local relative_path="$1"
    local output_path="$2"
    local expected_sha256="$3"
    local local_path="$source_root/$relative_path"

    if [[ -f "$local_path" ]]; then
        cp "$local_path" "$output_path"
    else
        local install_ref="${KLAUS_INSTALL_REF:-main}"
        case "$install_ref" in
            ""|*..*|*[!A-Za-z0-9._/-]*)
                echo "KLAUS_INSTALL_REF contains unsupported characters." >&2
                exit 1
                ;;
        esac
        local asset_url="https://raw.githubusercontent.com/bgigurtsis/Klaus/$install_ref/$relative_path"
        echo "Downloading $(basename "$relative_path")..."
        curl --fail --location --silent --show-error "$asset_url" \
            --output "$output_path"
    fi
    verify_sha256 "$output_path" "$expected_sha256"
}

prepare_asset \
    "packaging/remarkable/install-tablet.sh" \
    "$work_dir/install-tablet.sh" \
    "$tablet_installer_sha256"
prepare_asset \
    "packaging/remarkable/klaus-remarkable-prepare" \
    "$work_dir/klaus-remarkable-prepare" \
    "$tablet_prepare_sha256"
prepare_asset \
    "packaging/remarkable/klaus-remarkable.service" \
    "$work_dir/klaus-remarkable.service" \
    "$tablet_service_sha256"
prepare_asset \
    "scripts/pair-remarkable.py" \
    "$work_dir/pair-remarkable.py" \
    "$pairing_client_sha256"
pairing_client="$work_dir/pair-remarkable.py"

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
