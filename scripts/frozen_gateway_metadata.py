from pathlib import Path
from typing import Callable, Iterable


CopyMetadata = Callable[[str], Iterable[tuple[str, str]]]
_STABLE_DESTINATION = Path("flywheel_verify.egg-info")


def flywheel_verify_metadata_datas(copy_metadata: CopyMetadata) -> list[tuple[str, str]]:
    """Return PyInstaller datas for Flywheel's own versionless metadata root."""
    datas: list[tuple[str, str]] = []
    seen_targets: set[tuple[str, str]] = set()
    for source, _destination in copy_metadata("flywheel-verify"):
        source_root = Path(source)
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or path.name == "direct_url.json":
                continue
            destination = _STABLE_DESTINATION / path.relative_to(source_root).parent
            destination_text = destination.as_posix()
            target = (destination_text.lower(), path.name.lower())
            if target in seen_targets:
                raise ValueError(
                    "duplicate flywheel-verify metadata target: "
                    f"{destination_text}/{path.name}"
                )
            seen_targets.add(target)
            datas.append((str(path), destination_text))
    return datas
