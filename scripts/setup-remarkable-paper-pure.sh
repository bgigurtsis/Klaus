#!/bin/bash
set -euo pipefail

STREAM_VERSION="v1.3.1-paperpure.4"
STREAM_SHA512="c6dd3e5167a5e3a98a7bc0688a1142d3c6a53f2de07e1350dbf1ca31803dd7182eabc38ea48f7e543bd804cd92f0a8fb2d5ddb13c60ea7d08bb12ff4f93238e8"
LICENSE_SHA512="814f7ff90e542338425c7e6740ff7cd151143ee5ae32b40ea492d99e9498ac85ec5e42b33108fd065d03bf7d453866487054652a8a6f11339c6855e34be635ac"
TABLET_HOST="10.11.99.1"
TABLET_USER="root"
DRY_RUN=0
SKIP_PAIR=0

usage() {
	cat <<'EOF'
Usage: ./scripts/setup-remarkable-paper-pure.sh [options]

Install the Klaus screen service on a reMarkable Paper Pure over SSH.

Options:
  --host HOST    Use a Wi-Fi host instead of 10.11.99.1.
  --user USER    Use an SSH user instead of root.
  --skip-pair    Install the service without pairing Klaus.
  --dry-run      Check the tablet and downloads without changing it.
  -h, --help     Show this help.
EOF
}

while [ "$#" -gt 0 ]; do
	case "$1" in
		--host)
			[ "$#" -ge 2 ] || { echo "--host needs a value." >&2; exit 2; }
			TABLET_HOST=$2
			shift 2
			;;
		--user)
			[ "$#" -ge 2 ] || { echo "--user needs a value." >&2; exit 2; }
			TABLET_USER=$2
			shift 2
			;;
		--skip-pair)
			SKIP_PAIR=1
			shift
			;;
		--dry-run)
			DRY_RUN=1
			shift
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

case "$TABLET_HOST" in
	""|-*|*[!A-Za-z0-9._-]*)
		echo "The tablet host contains unsupported characters." >&2
		exit 2
		;;
esac
case "$TABLET_USER" in
	""|-*|*[!A-Za-z0-9._-]*)
		echo "The tablet user contains unsupported characters." >&2
		exit 2
		;;
esac

for command_name in curl python3 scp shasum ssh; do
	if ! command -v "$command_name" >/dev/null 2>&1; then
		echo "This setup needs $command_name." >&2
		exit 1
	fi
done

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PACKAGE_DIR="$REPO_DIR/packaging/remarkable"
for required_file in \
	install-on-tablet.sh \
	klaus-post-install \
	klaus-pre-deinstall \
	klaus-remarkable-pairing \
	klaus-remarkable-prepare \
	klaus-remarkable.service; do
	if [ ! -f "$PACKAGE_DIR/$required_file" ]; then
		echo "The setup file is missing: packaging/remarkable/$required_file" >&2
		exit 1
	fi
done

TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/klaus-remarkable.XXXXXX")
REMOTE_STAGE="/tmp/klaus-remarkable-setup-$$"
SSH_CONTROL="$TEMP_DIR/c"
SSH_OPTIONS=(-o "ConnectTimeout=10" -o "ControlMaster=auto" -o "ControlPersist=60" -o "ControlPath=$SSH_CONTROL")
SSH_TARGET="$TABLET_USER@$TABLET_HOST"

cleanup() {
	rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

echo "Checking $SSH_TARGET..."
ARCH=$(ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" uname -m)
if [ "$ARCH" != "aarch64" ]; then
	echo "Klaus currently supports the aarch64 Paper Pure only." >&2
	exit 1
fi

if ! ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" test -x /home/root/.vellum/bin/vellum; then
	echo "Install Vellum through reManager before you run this setup." >&2
	exit 1
fi

if ! ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" "/home/root/.vellum/bin/vellum list -I | grep -q '^rmppure-'"; then
	echo "Klaus currently supports reMarkable Paper Pure only." >&2
	exit 1
fi

OS_VERSION=$(ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" "cat /home/root/.vellum/state/osver 2>/dev/null || true")
case "$OS_VERSION" in
	3.27.*) ;;
	*)
		echo "Klaus currently supports Paper Pure software 3.27.x only. Found: ${OS_VERSION:-unknown}." >&2
		exit 1
		;;
esac

STREAM_URL="https://github.com/bgigurtsis/goMarkableStream/releases/download/$STREAM_VERSION/goMarkableStream-PaperPure"
LICENSE_URL="https://raw.githubusercontent.com/bgigurtsis/goMarkableStream/$STREAM_VERSION/LICENSE"
echo "Downloading the pinned Paper Pure service..."
curl --fail --location --silent --show-error "$STREAM_URL" -o "$TEMP_DIR/goMarkableStream"
curl --fail --location --silent --show-error "$LICENSE_URL" -o "$TEMP_DIR/LICENSE"

ACTUAL_STREAM_SHA512=$(shasum -a 512 "$TEMP_DIR/goMarkableStream" | awk '{print $1}')
ACTUAL_LICENSE_SHA512=$(shasum -a 512 "$TEMP_DIR/LICENSE" | awk '{print $1}')
if [ "$ACTUAL_STREAM_SHA512" != "$STREAM_SHA512" ]; then
	echo "The Paper Pure service checksum does not match." >&2
	exit 1
fi
if [ "$ACTUAL_LICENSE_SHA512" != "$LICENSE_SHA512" ]; then
	echo "The Paper Pure license checksum does not match." >&2
	exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
	echo "Dry run passed for Paper Pure $OS_VERSION. The tablet was not changed."
	exit 0
fi

STAGE_DIR="$TEMP_DIR/stage"
mkdir -p \
	"$STAGE_DIR/gms-root/home/root/.vellum/bin" \
	"$STAGE_DIR/gms-root/home/root/.vellum/licenses/gomarkablestream-paperpure" \
	"$STAGE_DIR/klaus-root/home/root/.vellum/bin" \
	"$STAGE_DIR/klaus-root/home/root/.vellum/licenses/klaus-remarkable" \
	"$STAGE_DIR/klaus-root/home/root/.vellum/share/klaus-remarkable" \
	"$STAGE_DIR/scripts"
install -m 755 "$TEMP_DIR/goMarkableStream" "$STAGE_DIR/gms-root/home/root/.vellum/bin/goMarkableStream"
install -m 644 "$TEMP_DIR/LICENSE" "$STAGE_DIR/gms-root/home/root/.vellum/licenses/gomarkablestream-paperpure/LICENSE"
printf '%s\n' "https://github.com/bgigurtsis/goMarkableStream/tree/$STREAM_VERSION" \
	> "$STAGE_DIR/gms-root/home/root/.vellum/licenses/gomarkablestream-paperpure/SOURCES"
install -m 755 "$PACKAGE_DIR/klaus-remarkable-pairing" "$STAGE_DIR/klaus-root/home/root/.vellum/bin/klaus-remarkable-pairing"
install -m 755 "$PACKAGE_DIR/klaus-remarkable-prepare" "$STAGE_DIR/klaus-root/home/root/.vellum/bin/klaus-remarkable-prepare"
install -m 644 "$PACKAGE_DIR/klaus-remarkable.service" "$STAGE_DIR/klaus-root/home/root/.vellum/share/klaus-remarkable/klaus-remarkable.service"
install -m 644 "$REPO_DIR/LICENSE" "$STAGE_DIR/klaus-root/home/root/.vellum/licenses/klaus-remarkable/LICENSE"
printf '%s\n' "https://github.com/bgigurtsis/Klaus" \
	> "$STAGE_DIR/klaus-root/home/root/.vellum/licenses/klaus-remarkable/SOURCES"
install -m 755 "$PACKAGE_DIR/klaus-post-install" "$STAGE_DIR/scripts/klaus-post-install"
install -m 755 "$PACKAGE_DIR/klaus-pre-deinstall" "$STAGE_DIR/scripts/klaus-pre-deinstall"
install -m 755 "$PACKAGE_DIR/install-on-tablet.sh" "$STAGE_DIR/install-on-tablet.sh"

echo "Copying the setup files to Paper Pure..."
ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" "mkdir -m 700 '$REMOTE_STAGE'"
scp "${SSH_OPTIONS[@]}" -r "$STAGE_DIR/." "$SSH_TARGET:$REMOTE_STAGE/"

if ! ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" "sh '$REMOTE_STAGE/install-on-tablet.sh' '$REMOTE_STAGE'"; then
	echo "Setup failed. The staging files remain at $REMOTE_STAGE for inspection." >&2
	exit 1
fi
ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" "rm -rf '$REMOTE_STAGE'"

if [ "$SKIP_PAIR" -eq 1 ]; then
	echo "The tablet service is installed. Pair Paper Pure in Klaus Settings."
	exit 0
fi

PAIRING_SOCKET="${KLAUS_DATA_DIR:-$HOME/.klaus}/remanager-pairing.sock"
if [ ! -S "$PAIRING_SOCKET" ]; then
	echo "The tablet service is installed, but Klaus is not open."
	echo "Open Klaus, then pair Paper Pure in Settings."
	echo "To view the private values, run: ssh $SSH_TARGET /home/root/.vellum/bin/klaus-remarkable-pairing"
	exit 0
fi

PAIRING_DATA=$(ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" "cat /home/root/.config/klaus-remarkable/service.env")
PAIR_USERNAME=$(printf '%s\n' "$PAIRING_DATA" | sed -n 's/^RK_SERVER_USERNAME=//p' | head -n 1)
PAIR_PASSWORD=$(printf '%s\n' "$PAIRING_DATA" | sed -n 's/^RK_SERVER_PASSWORD=//p' | head -n 1)
unset PAIRING_DATA
if [ -z "$PAIR_USERNAME" ] || [ -z "$PAIR_PASSWORD" ]; then
	echo "The tablet service is installed, but its pairing values are missing." >&2
	exit 1
fi

PAIR_HOSTNAME=$(ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" "hostname 2>/dev/null || true")
case "$PAIR_HOSTNAME" in
	""|*[!A-Za-z0-9_-]*) PAIR_HOSTNAME="" ;;
esac
PAIR_WIFI_ADDRESSES=$(
	ssh "${SSH_OPTIONS[@]}" "$SSH_TARGET" \
		"ip -4 -o addr show scope global 2>/dev/null | awk '{print \$4}' | cut -d/ -f1" |
		awk '$1 != "10.11.99.1" && $1 ~ /^[0-9.]+$/ { print $1 }'
)
PAIR_ADDRESSES=""
if [ "$TABLET_HOST" != "10.11.99.1" ]; then
	PAIR_ADDRESSES="https://$TABLET_HOST:2001"
fi
if [ -n "$PAIR_HOSTNAME" ]; then
	PAIR_ADDRESSES="${PAIR_ADDRESSES:+$PAIR_ADDRESSES
}https://$PAIR_HOSTNAME.local.:2001"
fi
while IFS= read -r wifi_address; do
	[ -n "$wifi_address" ] || continue
	PAIR_ADDRESSES="${PAIR_ADDRESSES:+$PAIR_ADDRESSES
}https://$wifi_address:2001"
done <<< "$PAIR_WIFI_ADDRESSES"
if [ -z "$PAIR_ADDRESSES" ]; then
	echo "Connect Paper Pure to Wi-Fi, then run setup again." >&2
	exit 1
fi

PAIR_RESULT=$(
	PAIR_ADDRESSES="$PAIR_ADDRESSES" \
	PAIR_USERNAME="$PAIR_USERNAME" \
	PAIR_PASSWORD="$PAIR_PASSWORD" \
	python3 - "$PAIRING_SOCKET" <<'PY'
import json
import os
import socket
import sys

last_message = "Klaus could not reach Paper Pure over Wi-Fi."
for address in dict.fromkeys(os.environ["PAIR_ADDRESSES"].splitlines()):
    request = {
        "address": address,
        "username": os.environ["PAIR_USERNAME"],
        "password": os.environ["PAIR_PASSWORD"],
    }
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(40)
    client.connect(sys.argv[1])
    client.sendall(json.dumps(request).encode("utf-8") + b"\n")
    response = bytearray()
    while b"\n" not in response:
        chunk = client.recv(4096)
        if not chunk:
            break
        response.extend(chunk)
    client.close()
    result = json.loads(bytes(response).split(b"\n", 1)[0])
    last_message = result.get("message", "Pairing returned no message.")
    if result.get("ok"):
        print(last_message)
        print(f"Klaus will use {address} after USB-C is disconnected.")
        break
else:
    print(last_message)
    raise SystemExit(1)
PY
)
unset PAIR_PASSWORD
echo "$PAIR_RESULT"
