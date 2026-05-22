from __future__ import annotations

from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class ImageMatcher:
    def __init__(self, root: Path):
        self.root = root
        self.index = self._build_index(root)

    def _build_index(self, root: Path) -> dict[str, str]:
        index: dict[str, str] = {}
        if not root.exists():
            return index

        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            index.setdefault(path.stem.strip(), str(path))

        return index

    def find(self, original_sku: object) -> str | None:
        if original_sku is None:
            return None
        return self.index.get(str(original_sku).strip())

    def refresh(self) -> None:
        self.index = self._build_index(self.root)

    def find_with_refresh(self, original_sku: object) -> str | None:
        found = self.find(original_sku)
        if found:
            return found
        self.refresh()
        return self.find(original_sku)
