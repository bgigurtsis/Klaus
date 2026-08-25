#!/bin/sh
set -eu

payload_dir=${1:?missing payload directory}
vellum_bin=/home/root/.vellum/bin/vellum
apk_bin=/home/root/.vellum/bin/apk
mount_rw=/home/root/.vellum/bin/mount-rw
mount_restore=/home/root/.vellum/bin/mount-restore
config_dir=/home/root/.config/klaus-remarkable
config=$config_dir/service.env

log() {
	echo "$*" >&2
}

if [ "$(id -u)" -ne 0 ]; then
	log "The installer must connect as root."
	exit 1
fi

if [ "$(uname -m)" != "aarch64" ]; then
	log "This installer supports reMarkable Paper Pure only."
	exit 1
fi

if [ ! -x "$vellum_bin" ] || [ ! -x "$apk_bin" ]; then
	log "Set up this tablet in reManager before running the Klaus installer."
	exit 1
fi

if ! "$apk_bin" info -e rmppure >/dev/null 2>&1; then
	log "This installer supports reMarkable Paper Pure only."
	exit 1
fi

os_package=$("$apk_bin" info -v remarkable-os 2>/dev/null | head -n 1 || true)
case "$os_package" in
	remarkable-os-3.27.*) ;;
	*)
		log "Paper Pure must run reMarkable OS 3.27 for this streamer release."
		exit 1
		;;
esac

missing=""
if ! "$apk_bin" info -e mount-utils >/dev/null 2>&1; then
	missing="$missing mount-utils"
fi
framebuffer_package=$("$apk_bin" info -v framebuffer-spy 2>/dev/null | head -n 1 || true)
case "$framebuffer_package" in
	framebuffer-spy-19.*) ;;
	*) missing="$missing framebuffer-spy" ;;
esac
broker_package=$("$apk_bin" info -v xovi-message-broker 2>/dev/null | head -n 1 || true)
case "$broker_package" in
	xovi-message-broker-19.*) ;;
	*) missing="$missing xovi-message-broker" ;;
esac

if [ -n "$missing" ]; then
	log "Installing required Vellum packages:$missing"
	if ! "$vellum_bin" update >&2 || ! "$vellum_bin" add $missing >&2; then
		log "Install these packages in reManager, then run this installer again:$missing"
		exit 1
	fi
fi

framebuffer_package=$("$apk_bin" info -v framebuffer-spy 2>/dev/null | head -n 1 || true)
broker_package=$("$apk_bin" info -v xovi-message-broker 2>/dev/null | head -n 1 || true)
case "$framebuffer_package:$broker_package" in
	framebuffer-spy-19.*:xovi-message-broker-19.*) ;;
	*)
		log "Paper Pure needs framebuffer-spy 19 and xovi-message-broker 19."
		exit 1
		;;
esac

if [ ! -x "$mount_rw" ] || [ ! -x "$mount_restore" ]; then
	log "The Vellum mount-utils package is incomplete."
	exit 1
fi

install -Dm755 "$payload_dir/goMarkableStream" \
	/home/root/.vellum/bin/goMarkableStream
install -Dm755 "$payload_dir/klaus-remarkable-prepare" \
	/home/root/.vellum/bin/klaus-remarkable-prepare
install -Dm644 "$payload_dir/klaus-remarkable.service" \
	/home/root/.vellum/share/klaus-remarkable/klaus-remarkable.service

if ! [ -s "$config" ] \
	|| ! grep -q '^RK_SERVER_USERNAME=..*' "$config" \
	|| ! grep -q '^RK_SERVER_PASSWORD=..*' "$config"; then
	umask 077
	mkdir -p "$config_dir"
	password=$(/usr/bin/openssl rand -hex 24)
	cat > "$config" <<EOF
RK_SERVER_BIND_ADDR=:2001
RK_SERVER_USERNAME=klaus
RK_SERVER_PASSWORD=$password
RK_HTTPS=true
RK_TLS_AUTO_GENERATE=true
RK_TLS_CERT_DIR=$config_dir/certs
RK_JWT_ENABLED=true
RK_JWT_SECRET_DIR=$config_dir/secrets
RK_JWT_TOKEN_LIFETIME=1h
RK_TAILSCALE_ENABLED=false
EOF
	chmod 600 "$config"
fi

systemctl stop klaus-remarkable.service 2>/dev/null || true
[ ! -x /home/root/xovi/stock ] || /home/root/xovi/stock >&2
if grep -q '^overlay.*/etc' /proc/mounts; then
	mount --make-private /etc
fi
if ! "$mount_rw" >&2; then
	sleep 2
	"$mount_rw" >&2
fi
trap '"$mount_restore" >&2' EXIT
mkdir -p /etc/systemd/system/multi-user.target.wants
rm -f /etc/systemd/system/klaus-remarkable.service
cp /home/root/.vellum/share/klaus-remarkable/klaus-remarkable.service \
	/etc/systemd/system/klaus-remarkable.service
chmod 644 /etc/systemd/system/klaus-remarkable.service
ln -sfn /etc/systemd/system/klaus-remarkable.service \
	/etc/systemd/system/multi-user.target.wants/klaus-remarkable.service
"$mount_restore" >&2
trap - EXIT
[ ! -x /home/root/xovi/start ] || /home/root/xovi/start >&2
systemctl daemon-reload >&2
systemctl enable --now klaus-remarkable.service >&2
systemctl try-restart klaus-remarkable.service >&2
sleep 2
if ! systemctl is-active --quiet klaus-remarkable.service; then
	log "The Klaus Paper Pure service did not start."
	systemctl status --no-pager klaus-remarkable.service >&2 || true
	exit 1
fi

username=$(sed -n 's/^RK_SERVER_USERNAME=//p' "$config" | head -n 1)
password=$(sed -n 's/^RK_SERVER_PASSWORD=//p' "$config" | head -n 1)
printf '{"username":"%s","password":"%s"}\n' "$username" "$password"
