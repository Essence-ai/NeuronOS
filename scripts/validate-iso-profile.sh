#!/usr/bin/env bash
# NeuronOS ISO Profile Validator
# Checks the ISO profile for common issues before building

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROFILE="${PROJECT_DIR}/iso-profile"
ERRORS=0
WARNINGS=0
PASSES=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() {
    echo -e "${GREEN}PASS${NC}: $1"
    PASSES=$((PASSES + 1))
}

fail() {
    echo -e "${RED}FAIL${NC}: $1"
    ERRORS=$((ERRORS + 1))
}

warn() {
    echo -e "${YELLOW}WARN${NC}: $1"
    WARNINGS=$((WARNINGS + 1))
}

check() {
    local desc="$1"
    shift
    if eval "$@" >/dev/null 2>&1; then
        pass "$desc"
    else
        fail "$desc"
    fi
}

echo "=== NeuronOS ISO Profile Validator ==="
echo "Profile: ${PROFILE}"
echo ""

# ─── Structure checks ──────────────────────────────────────────────────

echo "--- Profile Structure ---"

check "profiledef.sh exists" "[ -f '${PROFILE}/profiledef.sh' ]"
check "packages.x86_64 exists" "[ -f '${PROFILE}/packages.x86_64' ]"
check "pacman.conf exists" "[ -f '${PROFILE}/pacman.conf' ]"
check "airootfs directory exists" "[ -d '${PROFILE}/airootfs' ]"

# ─── Package checks ────────────────────────────────────────────────────

echo ""
echo "--- Package List ---"

PKG_FILE="${PROFILE}/packages.x86_64"

if [ -f "$PKG_FILE" ]; then
    # Check for duplicates
    dupes=$(sort "$PKG_FILE" | grep -v '^#' | grep -v '^$' | uniq -d | wc -l)
    if [ "$dupes" -eq 0 ]; then
        pass "No duplicate packages"
    else
        fail "Found $dupes duplicate package(s):"
        sort "$PKG_FILE" | grep -v '^#' | grep -v '^$' | uniq -d | while read -r line; do
            echo "       - $line"
        done
    fi

    # Required packages (GNOME stack)
    check "gnome-shell included" "grep -q '^gnome-shell$' '${PKG_FILE}' || grep -q '^gnome$' '${PKG_FILE}'"
    check "GDM included" "grep -q '^gdm$' '${PKG_FILE}'"
    check "nautilus included" "grep -q '^nautilus$' '${PKG_FILE}'"

    # Required packages (VM stack)
    check "qemu-full or qemu-desktop included" "grep -q '^qemu' '${PKG_FILE}'"
    check "libvirt included" "grep -q '^libvirt$' '${PKG_FILE}'"
    check "python-gobject included" "grep -q '^python-gobject$' '${PKG_FILE}'"

    # Banned packages (wrong DE/DM)
    if grep -q '^sddm$' "$PKG_FILE"; then
        fail "SDDM found in packages (should use GDM)"
    else
        pass "No SDDM in packages"
    fi

    if grep -q '^lxqt$' "$PKG_FILE" || grep -q '^lxqt-' "$PKG_FILE"; then
        fail "LXQt found in packages (should use GNOME)"
    else
        pass "No LXQt in packages"
    fi

    if grep -q '^calamares$' "$PKG_FILE"; then
        fail "Calamares found in packages (should use archinstall)"
    else
        pass "No Calamares in packages"
    fi

    # Package count
    pkg_count=$(grep -v '^#' "$PKG_FILE" | grep -v '^$' | wc -l)
    echo "  (Total packages: $pkg_count)"
fi

# ─── GDM / Display Manager ─────────────────────────────────────────────

echo ""
echo "--- Display Manager ---"

check "GDM config exists" "[ -f '${PROFILE}/airootfs/etc/gdm/custom.conf' ]"

if [ -f "${PROFILE}/airootfs/etc/gdm/custom.conf" ]; then
    check "GDM auto-login configured" "grep -q 'AutomaticLogin' '${PROFILE}/airootfs/etc/gdm/custom.conf'"
fi

# Check that build-iso.sh creates the GDM symlink (build-time, not profile-time)
if [ -f "${PROJECT_DIR}/build-iso.sh" ]; then
    check "build-iso.sh enables GDM service" "grep -q 'gdm.service' '${PROJECT_DIR}/build-iso.sh'"
fi

# ─── Entry points ──────────────────────────────────────────────────────

echo ""
echo "--- Entry Points ---"

for ep in neuron-hardware-detect neuron-vm-manager neuron-store neuron-welcome; do
    ep_path="${PROFILE}/airootfs/usr/bin/${ep}"
    if [ -f "$ep_path" ]; then
        pass "$ep exists"
        if [ ! -x "$ep_path" ]; then
            warn "$ep is not executable (build-iso.sh should chmod)"
        fi
    else
        fail "$ep missing"
    fi
done

# ─── Desktop shortcuts ─────────────────────────────────────────────────

echo ""
echo "--- Desktop Shortcuts ---"

DESKTOP_DIR="${PROFILE}/airootfs/etc/skel/Desktop"
if [ -d "$DESKTOP_DIR" ]; then
    check "Desktop shortcuts exist" "ls '${DESKTOP_DIR}'/*.desktop >/dev/null 2>&1"

    # Check for wrong DE references
    if grep -rq 'qterminal\|pcmanfm-qt\|lxqt' "$DESKTOP_DIR" 2>/dev/null; then
        fail "LXQt references found in desktop shortcuts"
    else
        pass "No LXQt references in desktop shortcuts"
    fi

    # Check that shortcuts use GNOME apps
    if [ -f "${DESKTOP_DIR}/terminal.desktop" ]; then
        check "Terminal shortcut uses gnome-terminal or kgx" "grep -q 'gnome-terminal\|kgx\|gnome-console' '${DESKTOP_DIR}/terminal.desktop'"
    fi

    if [ -f "${DESKTOP_DIR}/file-manager.desktop" ]; then
        check "File manager shortcut uses nautilus" "grep -q 'nautilus' '${DESKTOP_DIR}/file-manager.desktop'"
    fi
else
    fail "Desktop shortcuts directory missing"
fi

# ─── Themes ─────────────────────────────────────────────────────────────

echo ""
echo "--- Themes ---"

THEMES_DIR="${PROFILE}/airootfs/usr/share/neuron-os/themes"
check "NeuronOS theme exists" "[ -f '${THEMES_DIR}/neuron.css' ]"
check "Win11 theme exists" "[ -f '${THEMES_DIR}/win11.css' ]"
check "macOS theme exists" "[ -f '${THEMES_DIR}/macos.css' ]"

# Basic CSS validity - check that files are not empty and have CSS-like content
for theme in neuron win11 macos; do
    if [ -f "${THEMES_DIR}/${theme}.css" ]; then
        if [ -s "${THEMES_DIR}/${theme}.css" ]; then
            pass "${theme}.css is not empty"
        else
            fail "${theme}.css is empty"
        fi
    fi
done

# ─── GNOME dconf defaults ──────────────────────────────────────────────

echo ""
echo "--- GNOME Configuration ---"

check "dconf defaults exist" "[ -f '${PROFILE}/airootfs/etc/dconf/db/local.d/00-neuronos' ]"
check "dconf profile exists" "[ -f '${PROFILE}/airootfs/etc/dconf/profile/user' ]"

# ─── Python modules ────────────────────────────────────────────────────

echo ""
echo "--- Python Source Modules ---"

SRC_DIR="${PROJECT_DIR}/src"
for module in hardware_detect vm_manager store common onboarding migration updater; do
    if [ -d "${SRC_DIR}/${module}" ]; then
        pass "src/${module}/ exists"
        check "src/${module}/__init__.py exists" "[ -f '${SRC_DIR}/${module}/__init__.py' ]"
    else
        warn "src/${module}/ not found"
    fi
done

# ─── Data files ─────────────────────────────────────────────────────────

echo ""
echo "--- Data Files ---"

check "App catalog data exists" "[ -f '${PROJECT_DIR}/data/apps.json' ]"

# ─── VM Templates ───────────────────────────────────────────────────────

echo ""
echo "--- VM Templates ---"

TEMPLATE_DIR="${SRC_DIR}/vm_manager/templates"
if [ -d "$TEMPLATE_DIR" ]; then
    template_count=$(ls "$TEMPLATE_DIR"/*.j2 2>/dev/null | wc -l)
    if [ "$template_count" -gt 0 ]; then
        pass "Found $template_count Jinja2 template(s)"
    else
        warn "No Jinja2 templates found in ${TEMPLATE_DIR}"
    fi
else
    warn "VM templates directory not found"
fi

# ─── Security checks ───────────────────────────────────────────────────

echo ""
echo "--- Security Checks ---"

# Check for hardcoded secrets in Python source
if grep -rn 'password\s*=\s*["\x27][^"\x27]*["\x27]' "$SRC_DIR" --include='*.py' 2>/dev/null | grep -v 'test\|mock\|example\|#\|"""' | grep -v 'password.*=.*None\|password.*=.*""' | head -1 >/dev/null 2>&1; then
    warn "Potential hardcoded passwords found in source"
else
    pass "No hardcoded passwords detected"
fi

# Check for os.system usage
if grep -rn 'os\.system(' "$SRC_DIR" --include='*.py' 2>/dev/null | head -1 >/dev/null 2>&1; then
    warn "os.system() usage found (prefer subprocess)"
else
    pass "No os.system() usage"
fi

# ─── Summary ────────────────────────────────────────────────────────────

echo ""
echo "=== Summary ==="
echo -e "  ${GREEN}Passed${NC}: $PASSES"
if [ "$WARNINGS" -gt 0 ]; then
    echo -e "  ${YELLOW}Warnings${NC}: $WARNINGS"
fi
if [ "$ERRORS" -gt 0 ]; then
    echo -e "  ${RED}Failed${NC}: $ERRORS"
    echo ""
    echo "Profile validation FAILED with $ERRORS error(s)"
    exit 1
else
    echo ""
    echo "All checks passed!"
    exit 0
fi
