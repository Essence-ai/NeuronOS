"""
NeuronOS VM Templates Package

Provides XML template loading and rendering for VM creation.
"""

from .loader import TemplateLoader, get_template_loader

__all__ = ["TemplateLoader", "get_template_loader"]
