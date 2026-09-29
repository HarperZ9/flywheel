"""Reviewed module slices for lane payloads that cannot ship whole.

A slice ships part of a lane's package: the modules its read-only MCP tools
need, with none of the runtime dependencies the rest of the package imports.
Each slice is reviewed here, with a reason for the slice and for every excluded
dependency. The generator records the slice and the exclusions in the row, and
the manifest check refuses a row whose slice or exclusions differ from this
file, so a row cannot declare its own exclusions.

The generator also proves the slice closed: every import that runs when a
slice module loads (module level, outside functions and ``TYPE_CHECKING``
blocks) must resolve inside the slice or to a dependency that is not excluded.
Deferred imports inside functions are allowed. They are the tools the slice
cannot run, which the tool policy marks not in build.
"""
from __future__ import annotations

import ast
from typing import Any, Iterable

from _lane_payload_source import GeneratorError

PAYLOAD_SLICES: dict[str, dict[str, Any]] = {
    "calibrate-pro": {
        "reason": (
            "Catalog slice: the MCP status, doctor, list-panels and panel-info tools. "
            "Calibration stays in the Calibrate Pro app, and list-targets needs numpy."),
        "modules": (
            "calibrate_pro",
            "calibrate_pro.diagnostics",
            "calibrate_pro.mcp",
            "calibrate_pro.panels",
            "calibrate_pro.panels.builtin_panels",
            "calibrate_pro.panels.database",
            "calibrate_pro.panels.panel_types",
            "calibrate_pro.runtime",
        ),
        "excluded_runtime_dependencies": (
            {"requirement": "numpy>=1.24",
             "reason": "Imported by calibration math and by the targets package behind "
                       "list-targets; the catalog tools import it only inside functions "
                       "they do not reach."},
            {"requirement": "scipy>=1.10",
             "reason": "Imported by the advanced, calibration, core, hdr, lut_system, "
                       "profiles and verification packages, all outside the slice."},
            {"requirement": "build-color>=1.0.0",
             "reason": "Imported by the core package, outside the slice."},
        ),
    },
}


def slice_for(lane: str) -> dict[str, Any] | None:
    return PAYLOAD_SLICES.get(lane)


def requirement_import_name(requirement: str) -> str:
    """``build-color>=1.0.0`` -> ``build_color``, the name an import uses."""
    name = requirement.strip()
    for stop in "<>=!~;[ ":
        name = name.split(stop, 1)[0]
    return name.lower().replace("-", "_").replace(".", "_")


def module_of(path: str, pkg: str, pkg_dir: str) -> str | None:
    """The dotted module a package file defines, or None for a data file."""
    if not path.endswith(".py") or not path.startswith(pkg_dir + "/"):
        return None
    parts = path[len(pkg_dir) + 1:-len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([pkg, *parts])


def slice_paths(paths: Iterable[str], pkg: str, pkg_dir: str,
                modules: Iterable[str]) -> list[str]:
    """The package files that belong to the slice: the sliced modules only."""
    wanted = set(modules)
    return [path for path in paths if module_of(path, pkg, pkg_dir) in wanted]


def split_runtime_dependencies(
    lane: str, deps: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    """(kept, excluded) runtime dependencies for a lane under its reviewed slice.

    Refuses a reviewed exclusion the pinned pyproject does not declare, so the
    review cannot drift from the source it describes."""
    spec = slice_for(lane)
    if spec is None:
        return list(deps), []
    excluded = [dict(item) for item in spec["excluded_runtime_dependencies"]]
    missing = [item["requirement"] for item in excluded if item["requirement"] not in deps]
    if missing:
        raise GeneratorError(
            f"{lane}: reviewed exclusions not in the pinned dependencies: {missing!r}")
    dropped = {item["requirement"] for item in excluded}
    return [dep for dep in deps if dep not in dropped], excluded


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def _load_time_imports(tree: ast.Module) -> Iterable[ast.Import | ast.ImportFrom]:
    """Import statements that run when the module loads."""
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.If) and _is_type_checking(node):
            stack.extend(node.orelse)
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
            continue
        stack.extend(ast.iter_child_nodes(node))


def _targets(node: ast.Import | ast.ImportFrom, module: str, is_pkg: bool) -> list[str]:
    """Absolute module names an import statement needs, submodules included."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = node.module or ""
    if node.level:
        anchor = module.split(".") if is_pkg else module.split(".")[:-1]
        anchor = anchor[:len(anchor) - (node.level - 1)]
        base = ".".join([*anchor, base] if base else anchor)
    return [base, *(f"{base}.{alias.name}" for alias in node.names)]


def check_slice_closure(sources: dict[str, bytes], *, pkg: str, pkg_dir: str,
                        modules: Iterable[str], excluded_imports: set[str]) -> None:
    """Raise GeneratorError unless the slice loads with nothing outside it."""
    by_module = {module_of(path, pkg, pkg_dir): path for path in sources}
    by_module.pop(None, None)
    wanted = set(modules)
    problems = [f"slice module {m} has no source" for m in sorted(wanted - set(by_module))]
    for module in sorted(wanted & set(by_module)):
        parts = module.split(".")
        problems += [f"slice module {module} lacks its package {'.'.join(parts[:i])}"
                     for i in range(1, len(parts)) if ".".join(parts[:i]) not in wanted]
        path = by_module[module]
        tree = ast.parse(sources[path].decode("utf-8"), filename=path)
        for node in _load_time_imports(tree):
            for target in _targets(node, module, path.endswith("__init__.py")):
                top = target.split(".", 1)[0]
                if top in excluded_imports:
                    problems.append(f"{module} imports excluded {target} at load time")
                elif top == pkg and target in by_module and target not in wanted:
                    problems.append(f"{module} imports {target} at load time, outside the slice")
    if problems:
        raise GeneratorError("payload slice is not closed: " + "; ".join(problems))
