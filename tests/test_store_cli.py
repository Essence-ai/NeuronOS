"""
Tests for NeuronOS Store CLI module.

Tests CLI argument parsing, subcommands, search, info, categories,
layers, and error handling -- all without actually installing apps.
"""

import argparse
import json
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from store.app_catalog import (
    AppCatalog, AppInfo, AppCategory,
    CompatibilityLayer, CompatibilityRating,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_catalog_file(tmp_path: Path) -> Path:
    """Create a temporary catalog JSON file with sample apps."""
    catalog_path = tmp_path / "apps.json"
    data = {
        "version": "1.0",
        "apps": [
            {
                "id": "firefox",
                "name": "Firefox",
                "description": "Open-source web browser",
                "category": "productivity",
                "layer": "native",
                "rating": "perfect",
                "package_name": "firefox",
                "tags": ["browser", "web"],
            },
            {
                "id": "photoshop",
                "name": "Adobe Photoshop",
                "description": "Professional image editor",
                "category": "creative",
                "layer": "vm_windows",
                "rating": "perfect",
                "requires_gpu_passthrough": True,
            },
            {
                "id": "steam",
                "name": "Steam",
                "description": "Gaming platform",
                "category": "gaming",
                "layer": "native",
                "rating": "perfect",
                "package_name": "steam",
                "tags": ["games", "gaming"],
            },
            {
                "id": "vscode",
                "name": "Visual Studio Code",
                "description": "Code editor",
                "category": "development",
                "layer": "flatpak",
                "rating": "perfect",
                "package_name": "com.visualstudio.code",
            },
            {
                "id": "wine_notepad",
                "name": "Notepad++",
                "description": "Text editor via Wine",
                "category": "utilities",
                "layer": "wine",
                "rating": "good",
            },
        ],
    }
    catalog_path.write_text(json.dumps(data))
    return catalog_path


def _loaded_catalog(tmp_path: Path) -> AppCatalog:
    """Return a loaded AppCatalog backed by a temp file."""
    path = _make_catalog_file(tmp_path)
    catalog = AppCatalog(path)
    catalog.load()
    return catalog


# ---------------------------------------------------------------------------
# Tests: Argument Parsing
# ---------------------------------------------------------------------------

class TestCLIArgParsing:
    """Verify the argparse configuration inside store.cli.main."""

    def _build_parser(self):
        """Build the same parser that main() builds, without executing."""
        from store.cli import main
        import store.cli as cli_module

        parser = argparse.ArgumentParser(
            prog="neuron-store",
            description="NeuronOS Application Store",
        )
        parser.add_argument("-v", "--verbose", action="store_true")
        subparsers = parser.add_subparsers(dest="command", help="Commands")

        # search
        search_p = subparsers.add_parser("search")
        search_p.add_argument("query", nargs="?", default="")
        search_p.add_argument("-c", "--category")
        search_p.add_argument("-l", "--layer")

        # info
        info_p = subparsers.add_parser("info")
        info_p.add_argument("app_id")

        # install
        install_p = subparsers.add_parser("install")
        install_p.add_argument("app_id")

        # uninstall
        uninstall_p = subparsers.add_parser("uninstall")
        uninstall_p.add_argument("app_id")

        # list
        subparsers.add_parser("list")

        # categories
        subparsers.add_parser("categories")

        # layers
        subparsers.add_parser("layers")

        return parser

    @pytest.mark.unit
    def test_search_subcommand_parses(self):
        parser = self._build_parser()
        args = parser.parse_args(["search", "firefox"])
        assert args.command == "search"
        assert args.query == "firefox"

    @pytest.mark.unit
    def test_search_with_category_flag(self):
        parser = self._build_parser()
        args = parser.parse_args(["search", "-c", "gaming"])
        assert args.category == "gaming"

    @pytest.mark.unit
    def test_search_with_layer_flag(self):
        parser = self._build_parser()
        args = parser.parse_args(["search", "-l", "native"])
        assert args.layer == "native"

    @pytest.mark.unit
    def test_info_subcommand_parses(self):
        parser = self._build_parser()
        args = parser.parse_args(["info", "firefox"])
        assert args.command == "info"
        assert args.app_id == "firefox"

    @pytest.mark.unit
    def test_install_subcommand_parses(self):
        parser = self._build_parser()
        args = parser.parse_args(["install", "firefox"])
        assert args.command == "install"
        assert args.app_id == "firefox"

    @pytest.mark.unit
    def test_uninstall_subcommand_parses(self):
        parser = self._build_parser()
        args = parser.parse_args(["uninstall", "firefox"])
        assert args.command == "uninstall"
        assert args.app_id == "firefox"

    @pytest.mark.unit
    def test_list_subcommand_parses(self):
        parser = self._build_parser()
        args = parser.parse_args(["list"])
        assert args.command == "list"

    @pytest.mark.unit
    def test_categories_subcommand_parses(self):
        parser = self._build_parser()
        args = parser.parse_args(["categories"])
        assert args.command == "categories"

    @pytest.mark.unit
    def test_layers_subcommand_parses(self):
        parser = self._build_parser()
        args = parser.parse_args(["layers"])
        assert args.command == "layers"

    @pytest.mark.unit
    def test_verbose_flag(self):
        parser = self._build_parser()
        args = parser.parse_args(["-v", "search", "test"])
        assert args.verbose is True

    @pytest.mark.unit
    def test_no_command_sets_none(self):
        parser = self._build_parser()
        args = parser.parse_args([])
        assert args.command is None


# ---------------------------------------------------------------------------
# Tests: Search Functionality
# ---------------------------------------------------------------------------

class TestCLISearch:
    """Test the cmd_search function (via catalog, not real CLI invocation)."""

    @pytest.mark.unit
    def test_search_finds_by_name(self, tmp_path):
        catalog = _loaded_catalog(tmp_path)
        results = catalog.search("Firefox")
        assert len(results) == 1
        assert results[0].id == "firefox"

    @pytest.mark.unit
    def test_search_finds_by_tag(self, tmp_path):
        catalog = _loaded_catalog(tmp_path)
        results = catalog.search("browser")
        assert len(results) == 1
        assert results[0].id == "firefox"

    @pytest.mark.unit
    def test_search_finds_by_description(self, tmp_path):
        catalog = _loaded_catalog(tmp_path)
        results = catalog.search("Gaming platform")
        assert len(results) == 1
        assert results[0].id == "steam"

    @pytest.mark.unit
    def test_search_returns_empty_for_unknown(self, tmp_path):
        catalog = _loaded_catalog(tmp_path)
        results = catalog.search("nonexistent_app_xyz")
        assert len(results) == 0

    @pytest.mark.unit
    def test_cmd_search_with_mocked_catalog(self, tmp_path, capsys):
        """Test cmd_search function through its public interface."""
        from store.cli import cmd_search

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace(query="firefox", category=None, layer=None)
            ret = cmd_search(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "firefox" in captured.out.lower()

    @pytest.mark.unit
    def test_cmd_search_no_results(self, tmp_path, capsys):
        from store.cli import cmd_search

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace(query="nonexistent_xyz", category=None, layer=None)
            ret = cmd_search(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "No apps found" in captured.out

    @pytest.mark.unit
    def test_cmd_search_invalid_category(self, tmp_path, capsys):
        from store.cli import cmd_search

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace(query="", category="bogus_cat", layer=None)
            ret = cmd_search(args)

        assert ret == 1

    @pytest.mark.unit
    def test_cmd_search_invalid_layer(self, tmp_path, capsys):
        from store.cli import cmd_search

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace(query="", category=None, layer="bogus_layer")
            ret = cmd_search(args)

        assert ret == 1


# ---------------------------------------------------------------------------
# Tests: Info Command
# ---------------------------------------------------------------------------

class TestCLIInfo:
    """Test the cmd_info function."""

    @pytest.mark.unit
    def test_info_shows_app_details(self, tmp_path, capsys):
        from store.cli import cmd_info

        catalog = _loaded_catalog(tmp_path)
        mock_installer = MagicMock()
        mock_installer.is_installed.return_value = False

        with patch("store.cli.get_catalog", return_value=catalog), \
             patch("store.cli.AppInstaller", return_value=mock_installer):
            args = argparse.Namespace(app_id="firefox")
            ret = cmd_info(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "Firefox" in captured.out
        assert "native" in captured.out

    @pytest.mark.unit
    def test_info_app_not_found(self, tmp_path, capsys):
        from store.cli import cmd_info

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace(app_id="nonexistent_app")
            ret = cmd_info(args)

        assert ret == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()


# ---------------------------------------------------------------------------
# Tests: Categories Command
# ---------------------------------------------------------------------------

class TestCLICategories:
    """Test the cmd_categories function."""

    @pytest.mark.unit
    def test_categories_lists_populated_categories(self, tmp_path, capsys):
        from store.cli import cmd_categories

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace()
            ret = cmd_categories(args)

        assert ret == 0
        captured = capsys.readouterr()
        # Our sample catalog has productivity, creative, gaming, development, utilities
        assert "productivity" in captured.out
        assert "gaming" in captured.out
        assert "creative" in captured.out

    @pytest.mark.unit
    def test_categories_shows_counts(self, tmp_path, capsys):
        from store.cli import cmd_categories

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace()
            cmd_categories(args)

        captured = capsys.readouterr()
        # "gaming" has 1 app
        assert "1 app" in captured.out


# ---------------------------------------------------------------------------
# Tests: Layers Command
# ---------------------------------------------------------------------------

class TestCLILayers:
    """Test the cmd_layers function."""

    @pytest.mark.unit
    def test_layers_groups_apps(self, tmp_path, capsys):
        from store.cli import cmd_layers

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace()
            ret = cmd_layers(args)

        assert ret == 0
        captured = capsys.readouterr()
        # We have native, vm_windows, flatpak, wine layers populated
        assert "NATIVE" in captured.out
        assert "firefox" in captured.out
        assert "steam" in captured.out


# ---------------------------------------------------------------------------
# Tests: Install / Uninstall (mocked)
# ---------------------------------------------------------------------------

class TestCLIInstallUninstall:
    """Test install/uninstall commands with mocked AppInstaller."""

    @pytest.mark.unit
    def test_install_unknown_app_returns_error(self, tmp_path, capsys):
        from store.cli import cmd_install

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace(app_id="nonexistent_app")
            ret = cmd_install(args)

        assert ret == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()

    @pytest.mark.unit
    def test_install_already_installed(self, tmp_path, capsys):
        from store.cli import cmd_install

        catalog = _loaded_catalog(tmp_path)
        mock_installer = MagicMock()
        mock_installer.is_installed.return_value = True

        with patch("store.cli.get_catalog", return_value=catalog), \
             patch("store.cli.AppInstaller", return_value=mock_installer):
            args = argparse.Namespace(app_id="firefox")
            ret = cmd_install(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "already installed" in captured.out.lower()

    @pytest.mark.unit
    def test_install_success(self, tmp_path, capsys):
        from store.cli import cmd_install

        catalog = _loaded_catalog(tmp_path)
        mock_installer = MagicMock()
        mock_installer.is_installed.return_value = False
        mock_installer.install.return_value = True

        with patch("store.cli.get_catalog", return_value=catalog), \
             patch("store.cli.AppInstaller", return_value=mock_installer):
            args = argparse.Namespace(app_id="firefox")
            ret = cmd_install(args)

        assert ret == 0
        mock_installer.install.assert_called_once()

    @pytest.mark.unit
    def test_install_failure(self, tmp_path, capsys):
        from store.cli import cmd_install

        catalog = _loaded_catalog(tmp_path)
        mock_installer = MagicMock()
        mock_installer.is_installed.return_value = False
        mock_installer.install.return_value = False

        with patch("store.cli.get_catalog", return_value=catalog), \
             patch("store.cli.AppInstaller", return_value=mock_installer):
            args = argparse.Namespace(app_id="firefox")
            ret = cmd_install(args)

        assert ret == 1

    @pytest.mark.unit
    def test_uninstall_unknown_app(self, tmp_path, capsys):
        from store.cli import cmd_uninstall

        catalog = _loaded_catalog(tmp_path)
        with patch("store.cli.get_catalog", return_value=catalog):
            args = argparse.Namespace(app_id="nonexistent_app")
            ret = cmd_uninstall(args)

        assert ret == 1

    @pytest.mark.unit
    def test_uninstall_not_installed(self, tmp_path, capsys):
        from store.cli import cmd_uninstall

        catalog = _loaded_catalog(tmp_path)
        mock_installer = MagicMock()
        mock_installer.is_installed.return_value = False

        with patch("store.cli.get_catalog", return_value=catalog), \
             patch("store.cli.AppInstaller", return_value=mock_installer):
            args = argparse.Namespace(app_id="firefox")
            ret = cmd_uninstall(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "not installed" in captured.out.lower()

    @pytest.mark.unit
    def test_uninstall_success(self, tmp_path, capsys):
        from store.cli import cmd_uninstall

        catalog = _loaded_catalog(tmp_path)
        mock_installer = MagicMock()
        mock_installer.is_installed.return_value = True
        mock_installer.uninstall.return_value = True

        with patch("store.cli.get_catalog", return_value=catalog), \
             patch("store.cli.AppInstaller", return_value=mock_installer):
            args = argparse.Namespace(app_id="firefox")
            ret = cmd_uninstall(args)

        assert ret == 0
        mock_installer.uninstall.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: List Command
# ---------------------------------------------------------------------------

class TestCLIList:
    """Test the cmd_list function."""

    @pytest.mark.unit
    def test_list_no_apps_installed(self, tmp_path, capsys):
        from store.cli import cmd_list

        catalog = _loaded_catalog(tmp_path)
        mock_installer = MagicMock()
        mock_installer.is_installed.return_value = False

        with patch("store.cli.get_catalog", return_value=catalog), \
             patch("store.cli.AppInstaller", return_value=mock_installer):
            args = argparse.Namespace()
            ret = cmd_list(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "No apps installed" in captured.out

    @pytest.mark.unit
    def test_list_with_installed_apps(self, tmp_path, capsys):
        from store.cli import cmd_list

        catalog = _loaded_catalog(tmp_path)
        mock_installer = MagicMock()
        # Only "firefox" is installed
        mock_installer.is_installed.side_effect = lambda app: app.id == "firefox"

        with patch("store.cli.get_catalog", return_value=catalog), \
             patch("store.cli.AppInstaller", return_value=mock_installer):
            args = argparse.Namespace()
            ret = cmd_list(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "firefox" in captured.out
        assert "1" in captured.out  # count


# ---------------------------------------------------------------------------
# Tests: main() entry-point edge cases
# ---------------------------------------------------------------------------

class TestCLIMain:
    """Test the main() entry point."""

    @pytest.mark.unit
    def test_main_no_args_returns_1(self):
        """main() with no subcommand should print help and return 1."""
        from store.cli import main

        with patch("sys.argv", ["neuron-store"]):
            ret = main()

        assert ret == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
