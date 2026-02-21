#!/usr/bin/env bash
# customize_airootfs.sh - archiso in-chroot hook
# Runs inside the chroot AFTER all packages are installed and overlay files are in place.
# This is the correct place to compile the dconf database from our keyfile overlay.
set -euo pipefail

# ------------------------------------------------------------------
# Compile dconf binary database
# Without this, GNOME ignores /etc/dconf/db/local.d/00-neuronos and
# boots with the default Arch wallpaper/theme instead of NeuronOS branding.
# ------------------------------------------------------------------
dconf update

# ------------------------------------------------------------------
# Verify the liveuser home directory ownership
# build-iso.sh pre-populates /home/liveuser from /etc/skel before
# calling mkarchiso, so the UID/GID must match liveuser (1000:1000).
# ------------------------------------------------------------------
if [ -d /home/liveuser ]; then
    chown -R 1000:1000 /home/liveuser
fi

# ------------------------------------------------------------------
# Build Looking Glass client from source
# Looking Glass is not in the Arch repos. Without this, GPU passthrough
# VMs have no display — the entire differentiator is dead.
# Build deps are already in packages.x86_64.
# ------------------------------------------------------------------
LOOKING_GLASS_VERSION="B7-rc1"
LOOKING_GLASS_DIR="/tmp/looking-glass-build"

echo "[NeuronOS] Building Looking Glass client ${LOOKING_GLASS_VERSION}..."
mkdir -p "$LOOKING_GLASS_DIR"
cd "$LOOKING_GLASS_DIR"

# Download source
curl -sL "https://looking-glass.io/artifact/${LOOKING_GLASS_VERSION}/source" -o looking-glass.tar.gz \
    || curl -sL "https://github.com/gnif/LookingGlass/archive/refs/tags/${LOOKING_GLASS_VERSION}.tar.gz" -o looking-glass.tar.gz

mkdir -p source
tar xzf looking-glass.tar.gz -C source --strip-components=1
cd source/client

# Build
mkdir build && cd build
cmake \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DENABLE_WAYLAND=ON \
    -DENABLE_X11=ON \
    -DENABLE_PULSEAUDIO=ON \
    -DENABLE_PIPEWIRE=ON \
    ..
make -j"$(nproc)"
make install

echo "[NeuronOS] Looking Glass client installed to /usr/bin/looking-glass-client"

# Cleanup build artifacts
cd /
rm -rf "$LOOKING_GLASS_DIR"

# Self-cleanup — archiso expects this script to remove itself
rm -- "$0"
