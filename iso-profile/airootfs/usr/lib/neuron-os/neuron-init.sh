#!/bin/bash
# NeuronOS First Boot Setup
# Ensures critical services are running

# Start NetworkManager if not running
if ! systemctl is-active --quiet NetworkManager; then
    systemctl start NetworkManager
fi

# Start libvirtd if not running
if ! systemctl is-active --quiet libvirtd; then
    systemctl start libvirtd
fi
