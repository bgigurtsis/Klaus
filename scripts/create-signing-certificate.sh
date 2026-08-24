#!/bin/bash

# Creates a self-signed code-signing certificate in the login keychain so
# install-macos-app.sh can sign Klaus.app with a stable identity instead of
# the linker's ad-hoc signature. Run this once, by hand: macOS prompts for
# your password when the certificate is marked trusted for code signing.

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "This script requires macOS." >&2
    exit 1
fi

identity_name="${1:-Klaus Code Signing}"
keychain="$HOME/Library/Keychains/login.keychain-db"

if security find-identity -v -p codesigning 2>/dev/null \
    | grep -Fq "\"$identity_name\""; then
    echo "The identity \"$identity_name\" already exists. Nothing to do."
    exit 0
fi

work_dir="$(mktemp -d)"
cleanup() {
    rm -rf "$work_dir"
}
trap cleanup EXIT

cat >"$work_dir/openssl.cnf" <<CONF
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
CN = $identity_name
[ext]
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, codeSigning
basicConstraints = critical, CA:false
CONF

openssl req -x509 -newkey rsa:2048 -days 3650 -nodes \
    -config "$work_dir/openssl.cnf" \
    -keyout "$work_dir/key.pem" -out "$work_dir/cert.pem"
openssl pkcs12 -export -name "$identity_name" \
    -inkey "$work_dir/key.pem" -in "$work_dir/cert.pem" \
    -out "$work_dir/identity.p12" -passout pass:klaus-signing

security import "$work_dir/identity.p12" -k "$keychain" \
    -P klaus-signing -T /usr/bin/codesign

echo "Marking the certificate trusted for code signing."
echo "macOS asks for your login password now."
security add-trusted-cert -p codeSign -k "$keychain" "$work_dir/cert.pem"

if ! security find-identity -v -p codesigning \
    | grep -Fq "\"$identity_name\""; then
    echo "The identity did not become valid." >&2
    echo "Open Keychain Access, find \"$identity_name\", and set" >&2
    echo "Trust > Code Signing to Always Trust. Then rerun this script." >&2
    exit 1
fi

echo "Created the identity \"$identity_name\"."
echo "Reinstall the app to sign it: ./scripts/install-macos-app.sh"
