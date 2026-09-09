from __future__ import annotations

from pathlib import Path, PurePosixPath


def relative_image_path(image_path: str | Path, root: Path) -> Path | None:
    source_path = Path(image_path)
    try:
        return source_path.relative_to(root)
    except ValueError:
        # Historical imports may use another UNC alias for the same share.
        root_name = root.name.casefold()
        source_parts = source_path.parts
        for index in range(len(source_parts) - 1, -1, -1):
            if source_parts[index].casefold() != root_name:
                continue
            candidate = Path(*source_parts[index + 1 :])
            if candidate.parts and all(part not in {".", ".."} for part in candidate.parts):
                return candidate
        return None


def normalized_relative_image_path(value: str | Path) -> str:
    raw = str(value).strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Invalid relative image path")
    return path.as_posix()
