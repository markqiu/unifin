"""Hot-loader — dynamically register generated model and fetcher code.

After the CodeGenerator produces files, the Loader:
1. Writes files to disk.
2. Dynamically imports and executes them (triggering self-registration).
3. Updates __init__.py to ensure persistence across restarts.
"""

from __future__ import annotations

import importlib
import logging
import re
import sys
from pathlib import Path
from typing import Any

from unifin.evolve.schema import EvolvePlan, GeneratedFile

logger = logging.getLogger("unifin")


def _project_root() -> Path:
    """Return the project root (parent of src/)."""
    import unifin

    pkg_dir = Path(unifin.__file__).parent  # src/unifin/
    return pkg_dir.parent.parent  # project root


class HotLoader:
    """Write generated files and hot-register them into the running process."""

    def execute_plan(self, plan: EvolvePlan) -> dict[str, Any]:
        """Execute a confirmed plan: write files, import, register."""
        root = _project_root()
        report: dict[str, Any] = {
            "model_name": plan.model_name,
            "files_written": [],
            "files_failed": [],
            "registered": False,
            "init_updated": False,
        }

        # 1. Write files to disk
        for gf in plan.files:
            try:
                self._write_file(root, gf)
                report["files_written"].append(gf.path)
            except Exception as e:
                logger.error("Failed to write %s: %s", gf.path, e)
                report["files_failed"].append({"path": gf.path, "error": str(e)})

        if report["files_failed"]:
            plan.stage = plan.stage  # keep current stage
            return report

        # 2. Dynamic import — model first, then fetchers
        try:
            self._import_model(plan.need.model_name)
            for source in plan.sources:
                self._import_fetcher(source.provider, plan.need.model_name)
            report["registered"] = True
        except Exception as e:
            logger.error("Dynamic import failed: %s", e)
            report["files_failed"].append({"path": "<import>", "error": str(e)})
            return report

        # 3. Update __init__.py for persistence
        try:
            self._update_init_py(root, plan)
            report["init_updated"] = True
        except Exception as e:
            logger.warning("Failed to update __init__.py: %s (registration still active)", e)

        # 4. Update provider __init__.py
        try:
            for source in plan.sources:
                self._update_provider_init(root, source.provider, plan.need.model_name)
        except Exception as e:
            logger.warning("Failed to update provider __init__.py: %s", e)

        return report

    # ── File I/O ──

    @staticmethod
    def _write_file(root: Path, gf: GeneratedFile) -> None:
        abs_path = root / gf.path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(gf.content, encoding="utf-8")
        logger.info("Wrote %s", abs_path)

    # ── Dynamic import ──

    @staticmethod
    def _import_model(model_name: str) -> None:
        module_name = f"unifin.models.{model_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        importlib.import_module(module_name)
        logger.info("Dynamically imported model: %s", module_name)

    @staticmethod
    def _import_fetcher(provider: str, model_name: str) -> None:
        module_name = f"unifin.providers.{provider}.{model_name}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        importlib.import_module(module_name)
        logger.info("Dynamically imported fetcher: %s", module_name)

    # ── Persistence: update __init__.py ──

    @staticmethod
    def _update_init_py(root: Path, plan: EvolvePlan) -> None:
        init_path = root / "src" / "unifin" / "__init__.py"
        content = init_path.read_text(encoding="utf-8")

        model_name = plan.need.model_name
        import_line = f"from unifin.models import {model_name}"

        if import_line in content:
            return

        model_import_pattern = r"(from unifin\.models import \w+ as _m\d+.*\n)"
        matches = list(re.finditer(model_import_pattern, content))

        if matches:
            last_match = matches[-1]
            last_alias = re.search(r"_m(\d+)", last_match.group())
            next_num = int(last_alias.group(1)) + 1 if last_alias else len(matches) + 1

            new_import = (
                f"from unifin.models import {model_name}"
                f" as _m{next_num}  # noqa: F401, E402  # auto-evolved\n"
            )
            insert_pos = last_match.end()
            content = content[:insert_pos] + new_import + content[insert_pos:]
        else:
            provider_marker = "# ── Register providers ──"
            if provider_marker in content:
                pos = content.index(provider_marker)
                new_import = (
                    f"from unifin.models import {model_name}"
                    f" as _m_auto  # noqa: F401, E402  # auto-evolved\n\n"
                )
                content = content[:pos] + new_import + content[pos:]

        init_path.write_text(content, encoding="utf-8")
        logger.info("Updated __init__.py with model import: %s", model_name)

    @staticmethod
    def _update_provider_init(root: Path, provider: str, model_name: str) -> None:
        init_path = root / "src" / "unifin" / "providers" / provider / "__init__.py"

        if not init_path.exists():
            return

        content = init_path.read_text(encoding="utf-8")
        import_line = f"from unifin.providers.{provider} import {model_name}"

        if import_line in content:
            return

        new_import = (
            f"\nfrom unifin.providers.{provider}"
            f" import {model_name}  # noqa: F401  # auto-evolved\n"
        )
        content = content.rstrip() + new_import
        init_path.write_text(content, encoding="utf-8")
        logger.info("Updated %s/__init__.py with fetcher import: %s", provider, model_name)


# Global singleton
loader = HotLoader()
