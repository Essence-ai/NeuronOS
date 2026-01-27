# Phase 3: VM Management Core

**Status:** CORE FEATURE - Enables VM creation and lifecycle
**Estimated Time:** 5-7 days
**Prerequisites:** Phase 2 complete (hardware detection working)

---

## Recap: What We Are Building

**NeuronOS** provides seamless Windows/macOS software compatibility through:
- **GPU passthrough VMs** for professional software (Adobe, AutoCAD)
- Wine/Proton for simpler Windows apps
- Native Linux for everything else

**This Phase's Goal:** Create a working VM management system that:
1. Connects to libvirt daemon
2. Creates VMs from templates
3. Starts, stops, and manages VM lifecycle
4. Works from both CLI and (basic) GUI
5. Does NOT yet include GPU passthrough (that's Phase 5)

---

## Why This Phase Matters

Users need to create and manage VMs before GPU passthrough matters. This phase establishes:
- Reliable libvirt connection handling
- VM creation from XML templates
- Lifecycle management (start/stop/pause)
- Foundation for GUI in later phases

---

## Phase 3 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 3.1 | Libvirt connection works | Can connect to qemu:///system |
| 3.2 | VM templates render correctly | Jinja2 templates produce valid XML |
| 3.3 | VM creation works | Can create a basic VM |
| 3.4 | VM lifecycle works | Start, stop, pause, destroy |
| 3.5 | VM listing works | List all VMs with state |
| 3.6 | CLI works | `neuron-vm` commands work |

---

## Step 3.1: Verify Libvirt Connection

Test that we can connect to libvirt.

### Test Connection

```bash
cd /home/user/NeuronOS

python3 -c "
import sys
sys.path.insert(0, 'src')

# First, test raw libvirt
import libvirt

conn = libvirt.open('qemu:///system')
print(f'Connected to: {conn.getURI()}')
print(f'Hostname: {conn.getHostname()}')
print(f'Existing VMs: {len(conn.listAllDomains())}')
conn.close()
print('Connection closed successfully')
"
```

### Expected Output
- Shows connection URI
- Shows hostname
- Lists VMs (may be 0)
- Closes without error

### If Connection Fails

```bash
# Check libvirt service
sudo systemctl status libvirtd

# Check user is in libvirt group
groups | grep libvirt

# Check socket exists
ls -la /var/run/libvirt/libvirt-sock
```

### Verify LibvirtManager Class

```bash
python3 -c "
import sys
sys.path.insert(0, 'src')
from vm_manager.core.libvirt_manager import LibvirtManager

manager = LibvirtManager()
manager.connect()
print(f'Connected: {manager.is_connected}')
vms = manager.list_vms()
print(f'VMs: {len(vms)}')
manager.disconnect()
print('Disconnected')
"
```

### Verification Criteria for 3.1
- [ ] Raw libvirt connection works
- [ ] LibvirtManager.connect() succeeds
- [ ] LibvirtManager.list_vms() returns a list
- [ ] LibvirtManager.disconnect() works cleanly
- [ ] Reconnection after disconnect works

---

## Step 3.2: Verify VM Templates

NeuronOS uses Jinja2 templates to generate libvirt XML.

### Check Templates Exist

```bash
ls -la /home/user/NeuronOS/templates/
# Should show:
# - windows11-basic.xml.j2
# - windows11-passthrough.xml.j2
# - macos-sonoma-basic.xml.j2
# - macos-sonoma-passthrough.xml.j2
```

### Test Template Rendering

```bash
cd /home/user/NeuronOS

python3 -c "
import sys
sys.path.insert(0, 'src')
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

# Load templates
env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('windows11-basic.xml.j2')

# Render with test values
xml = template.render(
    name='test-vm',
    memory_mb=4096,
    vcpus=4,
    disk_path='/var/lib/libvirt/images/test.qcow2',
    disk_size_gb=64,
    iso_path='/path/to/windows.iso',
    uuid='12345678-1234-1234-1234-123456789abc',
    mac_address='52:54:00:12:34:56',
)

print('=== Generated XML (first 50 lines) ===')
for i, line in enumerate(xml.split('\n')[:50]):
    print(f'{i+1:3}: {line}')

# Verify it's valid XML
import xml.etree.ElementTree as ET
try:
    ET.fromstring(xml)
    print('\nXML is valid!')
except ET.ParseError as e:
    print(f'\nXML ERROR: {e}')
"
```

### Expected Output
- XML content with filled-in values
- "XML is valid!" message

### Required Template Variables

The basic Windows template should accept:
- `name`: VM name
- `memory_mb`: RAM in megabytes
- `vcpus`: Number of virtual CPUs
- `disk_path`: Path to disk image
- `disk_size_gb`: Disk size (for creation)
- `iso_path`: Path to installation ISO
- `uuid`: VM UUID
- `mac_address`: Network MAC address

### Verification Criteria for 3.2
- [ ] Template files exist
- [ ] Template renders without Jinja2 errors
- [ ] Rendered XML is valid
- [ ] All placeholder values are replaced
- [ ] No `{{ }}` remain in output

---

## Step 3.3: VM Creation

Test creating a real VM (without starting it).

### Prepare Test Resources

```bash
# Create test disk image
sudo mkdir -p /var/lib/libvirt/images
sudo qemu-img create -f qcow2 /var/lib/libvirt/images/neuron-test-vm.qcow2 20G

# Verify disk created
ls -lh /var/lib/libvirt/images/neuron-test-vm.qcow2
```

### Test VM Creation

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from vm_manager.core.libvirt_manager import LibvirtManager
from vm_manager.core.vm_config import VMConfig, VMType

# Create configuration
config = VMConfig(
    name='neuron-test-vm',
    vm_type=VMType.WINDOWS,
    memory_mb=4096,
    vcpus=4,
    disk_size_gb=20,
)

# Create VM
manager = LibvirtManager()
manager.connect()

try:
    # Check if VM already exists
    existing = [vm.name for vm in manager.list_vms()]
    if 'neuron-test-vm' in existing:
        print('Test VM already exists, destroying it first...')
        manager.destroy_vm('neuron-test-vm')

    # Create new VM
    print('Creating VM...')
    success = manager.create_vm(config)

    if success:
        print('VM created successfully!')
        vms = manager.list_vms()
        for vm in vms:
            if vm.name == 'neuron-test-vm':
                print(f'  Name: {vm.name}')
                print(f'  State: {vm.state}')
                print(f'  Memory: {vm.memory_mb}MB')
    else:
        print('VM creation failed')

except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
finally:
    manager.disconnect()
EOF
```

### Verify with virsh

```bash
virsh list --all | grep neuron-test-vm
# Should show the VM in "shut off" state

virsh dumpxml neuron-test-vm | head -30
# Should show valid XML configuration
```

### Verification Criteria for 3.3
- [ ] VMConfig dataclass works
- [ ] create_vm() succeeds
- [ ] VM appears in virsh list
- [ ] VM XML is valid
- [ ] VM state is "shut off"

---

## Step 3.4: VM Lifecycle Management

Test starting, stopping, and managing VMs.

### Test Lifecycle Operations

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
import time
sys.path.insert(0, 'src')
from vm_manager.core.libvirt_manager import LibvirtManager

manager = LibvirtManager()
manager.connect()

try:
    vm_name = 'neuron-test-vm'

    # Get initial state
    vms = manager.list_vms()
    vm = next((v for v in vms if v.name == vm_name), None)
    if not vm:
        print(f'VM {vm_name} not found!')
        sys.exit(1)

    print(f'Initial state: {vm.state}')

    # Try to start (may fail without ISO/bootable disk - that's OK)
    print('\nAttempting to start VM...')
    try:
        manager.start_vm(vm_name)
        time.sleep(2)
        vms = manager.list_vms()
        vm = next(v for v in vms if v.name == vm_name)
        print(f'After start: {vm.state}')
    except Exception as e:
        print(f'Start failed (expected without bootable disk): {e}')

    # Pause (if running)
    if vm.state.value == 'running':
        print('\nPausing VM...')
        manager.pause_vm(vm_name)
        time.sleep(1)
        vms = manager.list_vms()
        vm = next(v for v in vms if v.name == vm_name)
        print(f'After pause: {vm.state}')

        # Resume
        print('\nResuming VM...')
        manager.resume_vm(vm_name)
        time.sleep(1)
        vms = manager.list_vms()
        vm = next(v for v in vms if v.name == vm_name)
        print(f'After resume: {vm.state}')

        # Stop
        print('\nStopping VM...')
        manager.stop_vm(vm_name)
        time.sleep(2)
        vms = manager.list_vms()
        vm = next(v for v in vms if v.name == vm_name)
        print(f'After stop: {vm.state}')

    print('\nLifecycle test complete!')

except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
finally:
    manager.disconnect()
EOF
```

### Expected Behavior
- Start may fail without bootable disk (that's OK for now)
- If start works, pause/resume/stop should work
- All operations update VM state correctly

### Verification Criteria for 3.4
- [ ] start_vm() attempts to start (may fail without disk)
- [ ] pause_vm() pauses a running VM
- [ ] resume_vm() resumes a paused VM
- [ ] stop_vm() stops a running VM
- [ ] destroy_vm() forcefully stops a VM
- [ ] State transitions are correct

---

## Step 3.5: VM Information and Listing

Ensure we can get detailed information about VMs.

### Test VM Listing

```bash
cd /home/user/NeuronOS

python3 << 'EOF'
import sys
sys.path.insert(0, 'src')
from vm_manager.core.libvirt_manager import LibvirtManager

manager = LibvirtManager()
manager.connect()

try:
    vms = manager.list_vms()
    print(f'Found {len(vms)} VM(s):')

    for vm in vms:
        print(f'\n  Name: {vm.name}')
        print(f'  UUID: {vm.uuid}')
        print(f'  State: {vm.state}')
        print(f'  Memory: {vm.memory_mb} MB')
        print(f'  vCPUs: {vm.vcpus}')
        print(f'  Autostart: {vm.autostart}')

finally:
    manager.disconnect()
EOF
```

### Expected VMInfo Fields
- name: str
- uuid: str
- state: VMState enum
- memory_mb: int
- vcpus: int
- autostart: bool

### Verification Criteria for 3.5
- [ ] list_vms() returns list of VMInfo objects
- [ ] Each VM has all required fields
- [ ] State is correct VMState enum value
- [ ] Memory and vCPUs match configuration

---

## Step 3.6: Create CLI Commands

Create command-line interface for VM management.

### Create CLI Entry Point

Create or update `src/vm_manager/cli.py`:

```python
#!/usr/bin/env python3
"""NeuronOS VM Manager CLI."""

import argparse
import sys

def cmd_list(args):
    """List all VMs."""
    from vm_manager.core.libvirt_manager import LibvirtManager

    manager = LibvirtManager()
    manager.connect()

    try:
        vms = manager.list_vms()
        if not vms:
            print('No VMs found')
            return

        print(f'{"Name":<20} {"State":<12} {"Memory":<10} {"vCPUs":<6}')
        print('-' * 50)
        for vm in vms:
            print(f'{vm.name:<20} {vm.state.value:<12} {vm.memory_mb}MB{"":<4} {vm.vcpus:<6}')
    finally:
        manager.disconnect()

def cmd_start(args):
    """Start a VM."""
    from vm_manager.core.libvirt_manager import LibvirtManager

    manager = LibvirtManager()
    manager.connect()

    try:
        manager.start_vm(args.name)
        print(f'Started VM: {args.name}')
    except Exception as e:
        print(f'Failed to start: {e}')
        sys.exit(1)
    finally:
        manager.disconnect()

def cmd_stop(args):
    """Stop a VM."""
    from vm_manager.core.libvirt_manager import LibvirtManager

    manager = LibvirtManager()
    manager.connect()

    try:
        if args.force:
            manager.destroy_vm(args.name)
        else:
            manager.stop_vm(args.name)
        print(f'Stopped VM: {args.name}')
    except Exception as e:
        print(f'Failed to stop: {e}')
        sys.exit(1)
    finally:
        manager.disconnect()

def cmd_create(args):
    """Create a new VM."""
    from vm_manager.core.libvirt_manager import LibvirtManager
    from vm_manager.core.vm_config import VMConfig, VMType

    vm_type_map = {
        'windows': VMType.WINDOWS,
        'linux': VMType.LINUX,
        'macos': VMType.MACOS,
    }

    config = VMConfig(
        name=args.name,
        vm_type=vm_type_map.get(args.type, VMType.WINDOWS),
        memory_mb=args.memory * 1024,
        vcpus=args.cpus,
        disk_size_gb=args.disk,
    )

    if args.iso:
        from pathlib import Path
        config.iso_path = Path(args.iso)

    manager = LibvirtManager()
    manager.connect()

    try:
        success = manager.create_vm(config)
        if success:
            print(f'Created VM: {args.name}')
        else:
            print('Failed to create VM')
            sys.exit(1)
    except Exception as e:
        print(f'Error: {e}')
        sys.exit(1)
    finally:
        manager.disconnect()

def cmd_delete(args):
    """Delete a VM."""
    from vm_manager.core.libvirt_manager import LibvirtManager

    manager = LibvirtManager()
    manager.connect()

    try:
        manager.delete_vm(args.name, delete_disk=args.delete_disk)
        print(f'Deleted VM: {args.name}')
    except Exception as e:
        print(f'Failed to delete: {e}')
        sys.exit(1)
    finally:
        manager.disconnect()

def main():
    parser = argparse.ArgumentParser(
        prog='neuron-vm',
        description='NeuronOS VM Manager'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # list
    list_parser = subparsers.add_parser('list', help='List all VMs')
    list_parser.set_defaults(func=cmd_list)

    # start
    start_parser = subparsers.add_parser('start', help='Start a VM')
    start_parser.add_argument('name', help='VM name')
    start_parser.set_defaults(func=cmd_start)

    # stop
    stop_parser = subparsers.add_parser('stop', help='Stop a VM')
    stop_parser.add_argument('name', help='VM name')
    stop_parser.add_argument('--force', action='store_true', help='Force stop')
    stop_parser.set_defaults(func=cmd_stop)

    # create
    create_parser = subparsers.add_parser('create', help='Create a new VM')
    create_parser.add_argument('name', help='VM name')
    create_parser.add_argument('--type', choices=['windows', 'linux', 'macos'],
                               default='windows', help='VM type')
    create_parser.add_argument('--memory', type=int, default=8, help='Memory in GB')
    create_parser.add_argument('--cpus', type=int, default=4, help='Number of CPUs')
    create_parser.add_argument('--disk', type=int, default=64, help='Disk size in GB')
    create_parser.add_argument('--iso', help='Path to installation ISO')
    create_parser.set_defaults(func=cmd_create)

    # delete
    delete_parser = subparsers.add_parser('delete', help='Delete a VM')
    delete_parser.add_argument('name', help='VM name')
    delete_parser.add_argument('--delete-disk', action='store_true',
                               help='Also delete disk image')
    delete_parser.set_defaults(func=cmd_delete)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)

if __name__ == '__main__':
    main()
```

### Test CLI

```bash
cd /home/user/NeuronOS

# List VMs
python3 -m vm_manager.cli list

# Create a VM
python3 -m vm_manager.cli create cli-test-vm --memory 4 --cpus 2 --disk 20

# List again
python3 -m vm_manager.cli list

# Delete test VM
python3 -m vm_manager.cli delete cli-test-vm --delete-disk
```

### Verification Criteria for 3.6
- [ ] `list` command shows all VMs
- [ ] `create` command creates VMs
- [ ] `start` command starts VMs
- [ ] `stop` command stops VMs
- [ ] `delete` command removes VMs
- [ ] `--help` shows usage for each command

---

## Cleanup Test Resources

After testing, clean up:

```bash
# Delete test VM
virsh destroy neuron-test-vm 2>/dev/null
virsh undefine neuron-test-vm --remove-all-storage 2>/dev/null

# Verify cleanup
virsh list --all | grep neuron-test
```

---

## Verification Checklist

### Phase 3 is COMPLETE when ALL boxes are checked:

**Libvirt Connection**
- [ ] Can connect to qemu:///system
- [ ] Connection pooling/reuse works
- [ ] Disconnect cleans up properly
- [ ] Reconnection works

**Template Rendering**
- [ ] Jinja2 templates render correctly
- [ ] All variables are substituted
- [ ] Output XML is valid
- [ ] Templates exist for Windows, Linux, macOS

**VM Creation**
- [ ] VMConfig dataclass works
- [ ] Disk image creation works
- [ ] VM is defined in libvirt
- [ ] VM appears in virsh list

**VM Lifecycle**
- [ ] start_vm() works
- [ ] stop_vm() works
- [ ] pause_vm() works
- [ ] resume_vm() works
- [ ] destroy_vm() works

**VM Information**
- [ ] list_vms() returns correct data
- [ ] VM state is accurate
- [ ] Memory/CPU info is correct

**CLI**
- [ ] neuron-vm list works
- [ ] neuron-vm create works
- [ ] neuron-vm start works
- [ ] neuron-vm stop works
- [ ] neuron-vm delete works

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 4: Wine & Proton Integration](./PHASE_4_WINE_PROTON.md)**

Phase 4 will add Wine and Proton support for running Windows applications without a VM.
