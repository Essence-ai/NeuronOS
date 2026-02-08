"""
Tests for the NeuronOS theme system.

Verifies that all 3 GTK4 CSS theme files exist, are non-empty,
contain valid CSS-like content, and have no references to SDDM or LXQt
(NeuronOS uses GNOME/GDM, not LXQt/SDDM).
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Project root -- the repository checkout directory
PROJECT_ROOT = Path(__file__).parent.parent

# Theme directory relative to project root
THEME_DIR = PROJECT_ROOT / "iso-profile" / "airootfs" / "usr" / "share" / "neuron-os" / "themes"

# Expected theme files
EXPECTED_THEMES = ["neuron.css", "win11.css", "macos.css"]


# ---------------------------------------------------------------------------
# Tests: Theme Directory
# ---------------------------------------------------------------------------

class TestThemeDirectory:
    """Verify the theme directory structure."""

    @pytest.mark.unit
    def test_theme_directory_exists(self):
        assert THEME_DIR.exists(), f"Theme directory not found: {THEME_DIR}"

    @pytest.mark.unit
    def test_theme_directory_is_directory(self):
        assert THEME_DIR.is_dir(), f"Theme path is not a directory: {THEME_DIR}"

    @pytest.mark.unit
    def test_theme_directory_path_is_correct(self):
        """The path must be under iso-profile/airootfs/usr/share/neuron-os/themes/."""
        parts = THEME_DIR.parts
        assert "iso-profile" in parts
        assert "airootfs" in parts
        assert "neuron-os" in parts
        assert "themes" in parts


# ---------------------------------------------------------------------------
# Tests: Theme Files Exist
# ---------------------------------------------------------------------------

class TestThemeFilesExist:
    """Verify each expected CSS theme file is present."""

    @pytest.mark.unit
    def test_neuron_css_exists(self):
        assert (THEME_DIR / "neuron.css").exists(), "neuron.css not found"

    @pytest.mark.unit
    def test_win11_css_exists(self):
        assert (THEME_DIR / "win11.css").exists(), "win11.css not found"

    @pytest.mark.unit
    def test_macos_css_exists(self):
        assert (THEME_DIR / "macos.css").exists(), "macos.css not found"

    @pytest.mark.unit
    def test_all_three_themes_present(self):
        """Exactly 3 expected theme files must exist."""
        for name in EXPECTED_THEMES:
            assert (THEME_DIR / name).exists(), f"{name} not found in {THEME_DIR}"


# ---------------------------------------------------------------------------
# Tests: Theme Files Are Non-Empty
# ---------------------------------------------------------------------------

class TestThemeFilesNonEmpty:
    """Verify theme CSS files are not empty."""

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_theme_file_is_non_empty(self, filename):
        path = THEME_DIR / filename
        content = path.read_text()
        assert len(content.strip()) > 0, f"{filename} is empty"

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_theme_file_has_meaningful_size(self, filename):
        """Each theme should be at least a few hundred bytes."""
        path = THEME_DIR / filename
        size = path.stat().st_size
        assert size > 100, f"{filename} is suspiciously small ({size} bytes)"


# ---------------------------------------------------------------------------
# Tests: Valid CSS-like Content
# ---------------------------------------------------------------------------

class TestThemeCSSContent:
    """Verify theme files contain valid CSS-like content."""

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_has_css_selectors(self, filename):
        """CSS files must contain at least one selector with braces."""
        content = (THEME_DIR / filename).read_text()
        assert "{" in content and "}" in content, (
            f"{filename} lacks CSS selector braces"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_has_css_properties(self, filename):
        """CSS files must contain property declarations (colon + semicolon)."""
        content = (THEME_DIR / filename).read_text()
        assert ":" in content and ";" in content, (
            f"{filename} lacks CSS property declarations (colon/semicolon)"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_balanced_braces(self, filename):
        """Opening and closing braces should roughly balance."""
        content = (THEME_DIR / filename).read_text()
        opens = content.count("{")
        closes = content.count("}")
        assert opens == closes, (
            f"{filename} has unbalanced braces: {opens} open, {closes} close"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_contains_common_gtk_selectors(self, filename):
        """Theme files typically reference window, headerbar, button, etc."""
        content = (THEME_DIR / filename).read_text().lower()
        # At least one of these common GTK selectors should be present
        common_selectors = ["window", "headerbar", "button", "label", "entry", "box"]
        found = any(sel in content for sel in common_selectors)
        assert found, (
            f"{filename} does not contain any common GTK CSS selectors"
        )


# ---------------------------------------------------------------------------
# Tests: No SDDM or LXQt References
# ---------------------------------------------------------------------------

class TestNoWrongDEReferences:
    """NeuronOS uses GNOME/GDM. Theme files must not reference SDDM or LXQt."""

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_no_sddm_reference(self, filename):
        content = (THEME_DIR / filename).read_text().lower()
        assert "sddm" not in content, (
            f"{filename} references SDDM (NeuronOS uses GDM)"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_no_lxqt_reference(self, filename):
        content = (THEME_DIR / filename).read_text().lower()
        assert "lxqt" not in content, (
            f"{filename} references LXQt (NeuronOS uses GNOME)"
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("filename", EXPECTED_THEMES)
    def test_no_kde_plasma_reference(self, filename):
        """While not strictly required, KDE-specific references are unexpected."""
        content = (THEME_DIR / filename).read_text().lower()
        assert "plasma" not in content, (
            f"{filename} references KDE Plasma"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
