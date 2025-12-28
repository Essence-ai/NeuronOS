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

# Build modes and boot methods
buildmodes=('iso')
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito'
           'uefi-ia32.grub.esp' 'uefi-x64.grub.esp'
           'uefi-ia32.grub.eltorito' 'uefi-x64.grub.eltorito')

# Architecture
arch="x86_64"

# Package configuration
pacman_conf="pacman.conf"

# Root filesystem configuration
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')

# Bootstrap packages (minimum to bootstrap, rest from packages.x86_64)
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--long' '-19')

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
