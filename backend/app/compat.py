"""Start-up compatibility shims for locked-down Windows machines.

Windows Smart App Control can block a package's compiled extension modules (unsigned .pyd files). SQLAlchemy 2.1 ships
each of its Cython modules (``sqlalchemy/**/_*_cy``) next to the pure-Python source it was compiled from, but Python
always picks the binary first and fails. This finder tries the binary and, only when loading it raises ImportError,
loads the package's own pure-Python source instead (same behaviour, a little slower). The blocked binary is never run.
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys

PURE_FALLBACKS: list[str] = []  # modules loaded from pure-Python source because the binary was blocked
_PACKAGES = ("sqlalchemy.",)


class _PureSourceFallback(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):  # noqa: ANN001
        if not (name.startswith(_PACKAGES) and name.rsplit(".", 1)[-1].endswith("_cy")):
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader):
            return spec
        try:
            spec.loader.create_module(spec)
            return spec
        except ImportError:
            src = os.path.join(os.path.dirname(spec.origin), os.path.basename(spec.origin).split(".", 1)[0] + ".py") if spec.origin else ""
            if src and os.path.exists(src):
                PURE_FALLBACKS.append(name)
                return importlib.util.spec_from_file_location(name, src)
            return None


def install() -> None:
    if not any(isinstance(f, _PureSourceFallback) for f in sys.meta_path):
        sys.meta_path.insert(0, _PureSourceFallback())
