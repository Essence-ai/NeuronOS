#!/usr/bin/env bash
# NeuronOS ISO Profile Definition
# shellcheck disable=SC2034

# ISO metadata
iso_name="neuronos"
iso_label="NEURONOS_$(date +%Y%m)"
iso_publisher="NeuronOS Project <https://neuronos.org>"
iso_application="NeuronOS Live/Install Media"
iso_version="$(date +%Y.%m.%d)"
install_dir="arch"

# Build modes and boot methods (using current non-deprecated modes)
buildmodes=('iso')
bootmodes=('uefi.systemd-boot')

# Architecture
arch="x86_64"

# Package configuration
pacman_conf="pacman.conf"

# Root filesystem configuration
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')

# File permissions
# Format: [path]="uid:gid:mode"
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/etc/sudoers.d"]="0:0:750"
  ["/usr/bin/neuron-hardware-detect"]="0:0:755"
  ["/usr/bin/neuron-vm-manager"]="0:0:755"
  ["/usr/bin/neuron-store"]="0:0:755"
  ["/usr/lib/neuron-os"]="0:0:755"
)
