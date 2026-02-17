# Phase 3: VM Management Core

**Status:** ALREADY IMPLEMENTED (backend) - Verify and complete GUI
**Estimated Time:** 2-3 days
**Prerequisites:** Phase 2 complete (hardware detection verified)

---

## What Already Exists

The VM management backend is **production-ready** (~4,000 lines across 9+ files). The GUI is partially implemented.

### Existing Backend Files

| File | Lines | Status |
|------|-------|--------|
| `src/vm_manager/core/libvirt_manager.py` | 569 | 90% - high-level libvirt facade |
| `src/vm_manager/core/vm_creator.py` | 312 | 95% - disk creation, XML from Jinja2 templates |
| `src/vm_manager/core/vm_lifecycle.py` | 222 | 100% - start/stop/pause/resume with timeouts |
| `src/vm_manager/core/looking_glass.py` | 430 | 95% - Looking Glass client management |
| `src/vm_manager/core/guest_client.py` | 714 | 100% - TLS-encrypted guest agent protocol |
| `src/vm_manager/passthrough/gpu_attach.py` | 322 | 95% - sysfs-based GPU bind/unbind |
| `src/vm_manager/usb/usb_passthrough.py` | 463 | 95% - USB hot-plug with pyudev fallback |

### GUI Files (Partial)

| File | Lines | Status |
|------|-------|--------|
| `src/vm_manager/gui/app.py` | 911 | ~25% - skeleton, needs completion |
| `src/vm_manager/gui/app_qt.py` | 451 | Partial - Qt-specific components |

### Jinja2 VM Templates

Located in `src/vm_manager/templates/`:
- `windows10-basic.xml.j2` - Windows 10 without GPU passthrough
- `windows10-passthrough.xml.j2` - Windows 10 with GPU + IVSHMEM
- `windows11-basic.xml.j2` - Windows 11 without GPU passthrough
- `windows11-passthrough.xml.j2` - Windows 11 with GPU + IVSHMEM

---

## Phase 3 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 3.1 | Libvirt connection works | Connect/disconnect to qemu:///system |
| 3.2 | VM templates render valid XML | Jinja2 produces valid libvirt XML |
| 3.3 | VM creation works | Define a VM in libvirt |
| 3.4 | VM lifecycle works | Start/stop/pause/resume functions |
| 3.5 | Entry point works | `neuron-vm-manager` launches |

---

## Step 3.1: Verify Libvirt Connection

```bash
cd /home/user/NeuronOS
python3 -c "
import sys; sys.path.insert(0, 'src')
from vm_manager.core.libvirt_manager import LibvirtManager

manager = LibvirtManager()
manager.connect()
print(f'Connected: {manager.is_connected}')
vms = manager.list_vms()
print(f'Found {len(vms)} VMs')
for vm in vms:
    print(f'  {vm.name}: {vm.state} ({vm.memory_mb}MB, {vm.vcpus} vCPUs)')
manager.disconnect()
"
```

### If Connection Fails
```bash
sudo systemctl enable --now libvirtd
sudo usermod -aG libvirt $USER
# Log out and back in
```

---

## Step 3.2: Verify Template Rendering

```bash
python3 -c "
import sys, os; sys.path.insert(0, 'src')
from jinja2 import Environment, FileSystemLoader
import xml.etree.ElementTree as ET

env = Environment(loader=FileSystemLoader('src/vm_manager/templates'))
for tmpl_name in sorted(os.listdir('src/vm_manager/templates')):
    if not tmpl_name.endswith('.j2'): continue
    tmpl = env.get_template(tmpl_name)
    xml = tmpl.render(
        name='test', memory_mb=4096, vcpus=4,
        disk_path='/tmp/test.qcow2', disk_size_gb=64,
        iso_path='/tmp/windows.iso',
        uuid='12345678-1234-1234-1234-123456789abc',
        mac_address='52:54:00:12:34:56',
    )
    try:
        ET.fromstring(xml)
        print(f'{tmpl_name}: VALID XML ({len(xml)} bytes)')
    except ET.ParseError as e:
        print(f'{tmpl_name}: INVALID - {e}')
"
```

---

## Step 3.3: Verify VM Lifecycle Module

```bash
python3 -c "
import sys; sys.path.insert(0, 'src')
from vm_manager.core.vm_lifecycle import VMLifecycleManager
print('VMLifecycleManager methods:')
for m in ['start', 'stop', 'pause', 'resume', 'force_stop']:
    print(f'  {m}() - exists: {hasattr(VMLifecycleManager, m)}')
"
```

---

## What Needs Work: VM Manager GUI

The GUI (`src/vm_manager/gui/`) uses PyQt6. It needs these views:

1. **VM List** - table/cards showing all VMs with status (running/stopped/paused)
2. **Create VM Dialog** - form with name, OS type, memory, CPUs, disk size, ISO path
3. **VM Controls** - start/stop/pause/force-stop buttons per VM
4. **GPU Passthrough Toggle** - checkbox per VM to enable passthrough
5. **USB Device Panel** - list of host USB devices, click to attach/detach

All backend APIs exist for these. The GUI simply needs to call:
- `LibvirtManager.list_vms()` → `List[VMInfo]` with name, state, memory, vcpus
- `LibvirtManager.create_vm(config)` → creates from VMConfig
- `VMLifecycleManager.start/stop/pause/resume(vm_name)`
- `GPUPassthroughManager.attach(vm_name, pci_address)` / `.detach()`
- `USBPassthroughManager.scan_devices()` / `.attach(vm_name, device)`

---

## Verification Checklist

- [ ] `LibvirtManager` connects to qemu:///system without error
- [ ] `list_vms()` returns VM list (may be empty)
- [ ] All 4 Jinja2 templates render to valid XML
- [ ] `neuron-vm-manager` entry point script is valid Python
- [ ] Build script copies vm_manager module to ISO
- [ ] Templates copied to `/usr/share/neuron-os/templates/`

---

## Next Phase

Proceed to **[Phase 4: GPU Passthrough & Looking Glass](./PHASE_4_GPU_PASSTHROUGH.md)**
