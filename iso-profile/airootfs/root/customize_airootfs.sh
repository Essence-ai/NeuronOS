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

# Self-cleanup — archiso expects this script to remove itself
rm -- "$0"
