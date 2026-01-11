"""
VM Template Loader

Robust template loading from multiple paths with fallback support.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, BaseLoader

logger = logging.getLogger(__name__)


class TemplateLoader:
    """
    Loads VM XML templates from multiple locations.
    
    Search order:
    1. Local templates directory (within package)
    2. System templates (/usr/share/neuron-os/templates)
    3. User templates (~/.config/neuronos/templates)
    """
    
    TEMPLATE_PATHS = [
        Path(__file__).parent,  # templates/ folder
        Path("/usr/share/neuron-os/templates"),
        Path.home() / ".config/neuronos/templates",
    ]
    
    def __init__(self, additional_paths: Optional[List[Path]] = None):
        self._paths = list(self.TEMPLATE_PATHS)
        if additional_paths:
            self._paths.extend(additional_paths)
        
        self._env = self._create_environment()
    
    def _create_environment(self) -> Environment:
        """Create Jinja2 environment with all template paths."""
        loaders = []
        
        for path in self._paths:
            if path.exists() and path.is_dir():
                loaders.append(FileSystemLoader(str(path)))
                logger.debug(f"Added template path: {path}")
        
        if not loaders:
            # Create default directory
            default_path = self._paths[0]
            default_path.mkdir(parents=True, exist_ok=True)
            loaders.append(FileSystemLoader(str(default_path)))
            logger.warning(f"No template paths found, created: {default_path}")
        
        # Use ChoiceLoader to check multiple paths
        from jinja2 import ChoiceLoader
        
        return Environment(
            loader=ChoiceLoader(loaders),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
    
    def get_template(self, name: str) -> Optional[str]:
        """
        Get a template by name.
        
        Args:
            name: Template filename (e.g., "windows-passthrough.xml.j2")
            
        Returns:
            Template object or None
        """
        try:
            return self._env.get_template(name)
        except TemplateNotFound:
            logger.warning(f"Template not found: {name}")
            return None
    
    def render(self, name: str, **variables) -> Optional[str]:
        """
        Render a template with variables.
        
        Args:
            name: Template filename
            **variables: Template variables
            
        Returns:
            Rendered XML string or None
        """
        template = self.get_template(name)
        if template:
            return template.render(**variables)
        return None
    
    def list_templates(self) -> List[str]:
        """List all available templates."""
        templates = []
        for path in self._paths:
            if path.exists():
                templates.extend(f.name for f in path.glob("*.xml.j2"))
        return sorted(set(templates))
    
    def template_exists(self, name: str) -> bool:
        """Check if a template exists."""
        return self.get_template(name) is not None


# Global loader instance
_loader: Optional[TemplateLoader] = None


def get_template_loader() -> TemplateLoader:
    """Get the global template loader."""
    global _loader
    if _loader is None:
        _loader = TemplateLoader()
    return _loader
