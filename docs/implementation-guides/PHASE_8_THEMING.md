# Phase 8: Theming & UI Polish

**Status:** POLISH - Professional appearance
**Estimated Time:** 3-5 days
**Prerequisites:** Phase 7 complete (First-run working)

---

## Recap: What We Are Building

**NeuronOS** targets users coming from Windows. The UI should feel familiar while being distinctly NeuronOS.

**This Phase's Goal:**
1. Apply consistent theme across all applications
2. Provide Windows 11-like UI option
3. Ensure all NeuronOS apps match the theme
4. Polish icons, fonts, and visual elements

---

## Phase 8 Objectives

| Objective | Description | Verification |
|-----------|-------------|--------------|
| 8.1 | Default theme applied | Consistent colors |
| 8.2 | Windows-like theme works | Familiar UI for switchers |
| 8.3 | Icons consistent | NeuronOS branding |
| 8.4 | Fonts readable | Clear text everywhere |
| 8.5 | Dark mode works | Toggle light/dark |
| 8.6 | Theme persists | Applied after reboot |

---

## Step 8.1: Configure Default Theme

### Theme Structure

NeuronOS themes are in:
- `iso-profile/airootfs/usr/share/neuron-os/themes/`
- Individual app themes in `src/*/themes/`

### Check Theme Files

```bash
ls -la /home/user/NeuronOS/iso-profile/airootfs/usr/share/neuron-os/themes/
# Should show:
# - neuron.css (default)
# - win11.css (Windows 11 style)
# - macos.css (macOS style)
```

### Apply GTK Theme

For LXQt, configure in `iso-profile/airootfs/etc/skel/.config/lxqt/lxqt.conf`:

```ini
[General]
__userfile__=true

[Appearance]
theme=Breeze
icon_theme=Papirus
```

For GTK apps, configure `iso-profile/airootfs/etc/skel/.config/gtk-3.0/settings.ini`:

```ini
[Settings]
gtk-theme-name=Adwaita
gtk-icon-theme-name=Papirus
gtk-font-name=Noto Sans 11
gtk-application-prefer-dark-theme=false
```

### Verification Criteria for 8.1
- [ ] Theme files exist
- [ ] GTK theme applied
- [ ] LXQt theme applied
- [ ] Consistent appearance

---

## Step 8.2: Windows 11-Like Theme

Provide an option for users who want Windows-like experience.

### Windows 11 Theme Requirements

- Centered taskbar
- Rounded corners
- Windows 11 color scheme
- Familiar icons

### Apply Windows 11 Theme

For LXQt, the panel can be configured:

```bash
# Panel configuration
cat > /home/user/NeuronOS/iso-profile/airootfs/etc/skel/.config/lxqt/panel.conf << 'EOF'
[panel1]
alignment=0
animation-duration=0
backgroundColor=@Variant(\0\0\0\x43\x1\xff\xff\x18\x18\x18\x18\0\0)
desktop=0
fontColor=@Variant(\0\0\0\x43\x1\xff\xff\xff\xff\xff\xff\0\0)
hidable=false
iconSize=32
lineCount=1
lockPanel=true
opacity=100
panelSize=48
position=Bottom
reserveSpace=true
showDelay=0
width=100
widthPercent=true
EOF
```

### Theme Selection in Wizard

The onboarding wizard should offer theme choice:
- NeuronOS Default (modern)
- Windows 11 Style
- macOS Style

### Verification Criteria for 8.2
- [ ] Windows theme files exist
- [ ] Panel centered (optional)
- [ ] Colors match Windows 11
- [ ] User can select theme in wizard

---

## Step 8.3: Icon Consistency

### Install Icon Theme

Add to packages.x86_64:
```text
papirus-icon-theme
breeze-icons
```

### NeuronOS Application Icons

Create icons for NeuronOS apps:

```bash
ls /home/user/NeuronOS/iso-profile/airootfs/usr/share/icons/hicolor/scalable/apps/
# Should contain:
# - neuronos.svg
# - neuron-store.svg
# - neuron-vm-manager.svg
# - neuron-hardware-detect.svg
```

### Desktop Entry Icons

Ensure all .desktop files reference correct icons:

```bash
grep -r "Icon=" /home/user/NeuronOS/iso-profile/airootfs/etc/skel/Desktop/
```

### Verification Criteria for 8.3
- [ ] Icon theme installed
- [ ] NeuronOS icons exist
- [ ] Desktop entries use correct icons
- [ ] Icons visible at all sizes

---

## Step 8.4: Font Configuration

### Install Fonts

Add to packages.x86_64:
```text
ttf-dejavu
noto-fonts
ttf-liberation
ttf-roboto
```

### Configure Font Rendering

Create `iso-profile/airootfs/etc/fonts/local.conf`:

```xml
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <!-- Enable antialiasing -->
  <match target="font">
    <edit name="antialias" mode="assign">
      <bool>true</bool>
    </edit>
  </match>

  <!-- Enable hinting -->
  <match target="font">
    <edit name="hinting" mode="assign">
      <bool>true</bool>
    </edit>
    <edit name="hintstyle" mode="assign">
      <const>hintslight</const>
    </edit>
  </match>

  <!-- Enable subpixel rendering -->
  <match target="font">
    <edit name="rgba" mode="assign">
      <const>rgb</const>
    </edit>
  </match>

  <!-- Default fonts -->
  <alias>
    <family>sans-serif</family>
    <prefer>
      <family>Noto Sans</family>
      <family>DejaVu Sans</family>
    </prefer>
  </alias>

  <alias>
    <family>monospace</family>
    <prefer>
      <family>Noto Sans Mono</family>
      <family>DejaVu Sans Mono</family>
    </prefer>
  </alias>
</fontconfig>
```

### Verification Criteria for 8.4
- [ ] Fonts installed
- [ ] Antialiasing enabled
- [ ] Text renders clearly
- [ ] Consistent across apps

---

## Step 8.5: Dark Mode Support

### GTK Dark Mode

For GTK4/Adwaita apps:

```python
# In NeuronOS apps, respect system preference
import gi
gi.require_version('Adw', '1')
from gi.repository import Adw

style_manager = Adw.StyleManager.get_default()
# Options: DEFAULT, FORCE_LIGHT, FORCE_DARK
style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)
```

### Theme Toggle

Create a system preference toggle:

```python
def set_dark_mode(enabled: bool):
    """Set system-wide dark mode preference."""
    from pathlib import Path
    from utils.atomic_write import atomic_write_text

    # GTK settings
    gtk_settings = Path.home() / ".config/gtk-3.0/settings.ini"
    content = f"""[Settings]
gtk-application-prefer-dark-theme={'true' if enabled else 'false'}
"""
    atomic_write_text(gtk_settings, content)

    # LXQt settings
    lxqt_settings = Path.home() / ".config/lxqt/lxqt.conf"
    # Update theme here

    # Save preference
    neuron_config = Path.home() / ".config/neuronos/preferences.json"
    import json
    if neuron_config.exists():
        with open(neuron_config) as f:
            prefs = json.load(f)
    else:
        prefs = {}

    prefs['dark_mode'] = enabled

    from utils.atomic_write import atomic_write_json
    atomic_write_json(neuron_config, prefs)
```

### Verification Criteria for 8.5
- [ ] Dark mode preference stored
- [ ] GTK apps follow preference
- [ ] LXQt follows preference
- [ ] Toggle persists after reboot

---

## Step 8.6: Theme Persistence

### Apply Theme on Login

Create `iso-profile/airootfs/etc/profile.d/neuronos-theme.sh`:

```bash
#!/bin/bash
# Apply NeuronOS theme settings

NEURON_PREFS="$HOME/.config/neuronos/preferences.json"

if [ -f "$NEURON_PREFS" ]; then
    # Read dark mode preference
    DARK_MODE=$(python3 -c "import json; print(json.load(open('$NEURON_PREFS')).get('dark_mode', False))")

    if [ "$DARK_MODE" = "True" ]; then
        export GTK_THEME="Adwaita:dark"
    fi
fi
```

### Verification Criteria for 8.6
- [ ] Theme applied on login
- [ ] Survives reboot
- [ ] User changes persist
- [ ] No flickering on login

---

## Verification Checklist

### Phase 8 is COMPLETE when ALL boxes are checked:

**Default Theme**
- [ ] Theme files exist
- [ ] Applied to desktop
- [ ] Applied to applications
- [ ] Consistent colors

**Windows 11 Theme**
- [ ] Theme option available
- [ ] Panel configured
- [ ] Colors appropriate
- [ ] User can select

**Icons**
- [ ] Icon theme installed
- [ ] NeuronOS icons exist
- [ ] Desktop entries correct
- [ ] All sizes work

**Fonts**
- [ ] Fonts installed
- [ ] Rendering configured
- [ ] Text clear and readable

**Dark Mode**
- [ ] Toggle works
- [ ] Applications follow
- [ ] Preference saved

**Persistence**
- [ ] Theme survives reboot
- [ ] User changes kept
- [ ] No visual glitches

---

## Next Phase

Once all verification checks pass, proceed to **[Phase 9: Testing & Production](./PHASE_9_PRODUCTION.md)**

Phase 9 will add comprehensive testing and prepare for production release.
