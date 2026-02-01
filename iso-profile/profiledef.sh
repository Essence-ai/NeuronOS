#!/usr/bin/env bash
# NeuronOS ISO Profile
# shellcheck disable=SC2034

iso_name="neuronos"
iso_label="NEURONOS_$(date +%Y%m)"
iso_publisher="NeuronOS Project"
iso_application="NeuronOS Live/Install"
iso_version="$(date +%Y.%m.%d)"
install_dir="arch"
buildmodes=('iso')
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito' 'uefi-x64.systemd-boot.esp' 'uefi-x64.systemd-boot.eltorito')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/etc/gshadow"]="0:0:400"
  ["/etc/sudoers.d"]="0:0:750"
  ["/etc/sudoers.d/liveuser"]="0:0:440"
  ["/etc/skel/Desktop/install-neuronos.desktop"]="0:0:755"
)
