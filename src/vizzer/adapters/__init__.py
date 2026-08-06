"""Source-adapter registry and shared scan result."""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import ModuleType


@dataclass
class ScanResult:
    groups: list = field(default_factory=list)
    items: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def get_adapters(cfg) -> list[tuple[str, ModuleType]]:
    """Return enabled adapter modules in configured precedence order."""
    adapters = []
    for name in cfg.get("reconcile.precedence", []):
        if name == "dag_import":
            continue
        if cfg.get(f"sources.{name}.enabled", False):
            module = importlib.import_module(f".{name}", __name__)
            adapters.append((name, module))
    return adapters
