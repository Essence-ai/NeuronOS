"""
NeuronOS First-Boot Onboarding Wizard

Provides a friendly first-boot experience for new users:
- Welcome screen with NeuronOS introduction
- Hardware detection and compatibility check
- VM setup options (Windows/macOS)
- File migration from previous OS
- Quick tutorial
"""

from .wizard import OnboardingWizard
from .pages import (
    WelcomePage,
    HardwareCheckPage,
    VMSetupPage,
    MigrationPage,
    TutorialPage,
    CompletePage,
)

__all__ = [
    "OnboardingWizard",
    "WelcomePage",
    "HardwareCheckPage",
    "VMSetupPage",
    "MigrationPage",
    "TutorialPage",
    "CompletePage",
]
