# -*- coding: utf-8 -*-
"""Agent hooks package.

This package provides hook implementations for CoPawAgent that follow
AgentScope's hook interface (any Callable).

# ... lines 7-8 ...
Available Hooks:
    - BootstrapHook: First-time setup guidance


Example:
# ... lines 12-16 ...
    >>> from copaw.agents.hooks import BootstrapHook
    >>> from pathlib import Path
    >>>
    >>> # Create hooks (they are callables following AgentScope's interface)
    >>> bootstrap = BootstrapHook(Path("~/.copaw"), language="zh")
    >>>
    >>> # Register with agent using AgentScope's register_instance_hook
    >>> agent.register_instance_hook("pre_reasoning", "bootstrap", bootstrap)

"""

# ... line 29 ...
from .bootstrap import BootstrapHook


# ... lines 32-33 ...
__all__ = [
    "BootstrapHook",
]
