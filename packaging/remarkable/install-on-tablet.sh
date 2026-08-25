#!/bin/sh
set -eu

stage=${1:-}
case "$stage" in
	/tmp/klaus-remarkable-setup-*) ;;
	*)
		echo "The tablet staging path is invalid." >&2
		exit 1
		;;
esac

vellum=/home/root/.vellum/bin/vellum
if [ ! -x "$vellum" ]; then
	echo "Install Vellum through reManager before you run this setup." >&2
	exit 1
fi

if ! "$vellum" list -I | grep -q '^rmppure-'; then
	echo "Klaus currently supports reMarkable Paper Pure only." >&2
	exit 1
fi

os_version=$(cat /home/root/.vellum/state/osver 2>/dev/null || true)
case "$os_version" in
	3.27.*) ;;
	*)
		echo "Klaus currently supports Paper Pure software 3.27.x only." >&2
		exit 1
		;;
esac

echo "Installing signed Vellum dependencies..."
"$vellum" add framebuffer-spy xovi-message-broker mount-utils

cd "$stage"
"$vellum" mkpkg \
	--files gms-root \
	--info name:gomarkablestream-paperpure \
	--info version:1.3.1_pre4-r0 \
	--info arch:aarch64 \
	--info description:'Paper Pure preview of goMarkableStream for Klaus' \
	--info license:MIT \
	--info url:https://github.com/bgigurtsis/goMarkableStream \
	--info depends:'framebuffer-spy>=19 framebuffer-spy<20 xovi-message-broker>=19 xovi-message-broker<20 rmppure remarkable-os>=3.27 remarkable-os<3.28' \
	--info provides:'gomarkablestream=1.3.1_pre4-r0' \
	--output gomarkablestream-paperpure-1.3.1_pre4-r0.apk

"$vellum" mkpkg \
	--files klaus-root \
	--info name:klaus-remarkable \
	--info version:0.1.0-r16 \
	--info arch:aarch64 \
	--info description:'Manage the Paper Pure screenshot service used by Klaus' \
	--info license:MIT \
	--info url:https://github.com/bgigurtsis/Klaus \
	--info depends:'gomarkablestream-paperpure mount-utils rmppure remarkable-os>=3.27 remarkable-os<3.28' \
	--script post-install:scripts/klaus-post-install \
	--script post-upgrade:scripts/klaus-post-install \
	--script pre-deinstall:scripts/klaus-pre-deinstall \
	--output klaus-remarkable-0.1.0-r16.apk

"$vellum" verify --allow-untrusted gomarkablestream-paperpure-1.3.1_pre4-r0.apk
"$vellum" verify --allow-untrusted klaus-remarkable-0.1.0-r16.apk

echo "Installing the locally built Klaus packages..."
"$vellum" add --allow-untrusted gomarkablestream-paperpure-1.3.1_pre4-r0.apk
"$vellum" add --allow-untrusted klaus-remarkable-0.1.0-r16.apk

if [ "$(systemctl is-active klaus-remarkable.service)" != "active" ]; then
	echo "The Klaus Paper Pure service did not start." >&2
	exit 1
fi

echo "The Klaus Paper Pure service is active."
