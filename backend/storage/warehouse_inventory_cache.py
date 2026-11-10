"""Bounded reuse of already aggregated warehouse groups, never raw details."""
from __future__ import annotations

from collections import OrderedDict
from array import array
from dataclasses import dataclass
from decimal import Decimal
from sys import getsizeof
from threading import BoundedSemaphore, Condition
from time import monotonic
from typing import Callable
import zlib

import orjson


MAX_GROUPS = 50_000
MAX_BARCODE_GROUPS = 250_000
BARCODE_CHUNK_ROWS = 256
MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 8
TTL_SECONDS = 120


@dataclass(frozen=True)
class InventoryGroups:
    rows: tuple[bytes, ...]
    nonzero: tuple[int, ...]
    totals: bytes
    size: int

    @classmethod
    def from_result(cls, result: dict) -> InventoryGroups | None:
        if result["total"] > MAX_GROUPS:
            return None
        encoded = []
        encoded_size = 0
        for item in result["items"]:
            row = orjson.dumps(item)
            encoded_size += getsizeof(row)
            if encoded_size > MAX_BYTES:
                return None
            encoded.append(row)
        rows = tuple(encoded)
        nonzero = tuple(index for index, item in enumerate(result["items"]) if Decimal(item["ending_qty"]) != 0)
        totals = orjson.dumps(result["totals"])
        size = (getsizeof(rows) + sum(map(getsizeof, rows)) + getsizeof(nonzero)
                + sum(map(getsizeof, nonzero)) + getsizeof(totals))
        if size > MAX_BYTES:
            return None
        return cls(rows, nonzero, totals, size)

    def page(self, page: int, page_size: int, ending_nonzero: bool) -> dict:
        start = (page - 1) * page_size
        if ending_nonzero:
            rows = (self.rows[index] for index in self.nonzero[start:start + page_size])
            total = len(self.nonzero)
        else:
            rows = self.rows[start:start + page_size]
            total = len(self.rows)
        return {
            "items": [orjson.loads(row) for row in rows], "total": total,
            "page": page, "page_size": page_size, "totals": orjson.loads(self.totals),
        }


@dataclass(frozen=True)
class CompressedInventoryGroups:
    """Bounded chunks allow large barcode results to reuse the same byte budget."""
    chunks: tuple[bytes, ...]
    nonzero: bytes
    totals: bytes
    count: int
    size: int

    @classmethod
    def from_rows(cls, rows, totals, *, max_groups=MAX_BARCODE_GROUPS):
        chunks, batch = [], []
        positions = array("I")
        count = 0
        retained = 0
        for item in rows:
            if count >= max_groups:
                return None
            if Decimal(item["ending_qty"]) != 0:
                positions.append(count)
            batch.append(item)
            count += 1
            if len(batch) == BARCODE_CHUNK_ROWS:
                chunk = zlib.compress(orjson.dumps(batch), level=1)
                retained += getsizeof(chunk)
                if retained + getsizeof(positions) + getsizeof(chunks) > MAX_BYTES:
                    return None
                chunks.append(chunk)
                batch.clear()
        if batch:
            chunk = zlib.compress(orjson.dumps(batch), level=1)
            retained += getsizeof(chunk)
            chunks.append(chunk)
        chunks = tuple(chunks)
        nonzero = positions.tobytes()
        encoded_totals = orjson.dumps(totals)
        size = getsizeof(chunks) + retained + getsizeof(nonzero) + getsizeof(encoded_totals)
        if size > MAX_BYTES:
            return None
        return cls(chunks, nonzero, encoded_totals, count, size)

    def page(self, page: int, page_size: int, ending_nonzero: bool) -> dict:
        start = (page - 1) * page_size
        indices = memoryview(self.nonzero).cast("I") if ending_nonzero else range(self.count)
        chosen = indices[start:start + page_size]
        items = []
        last_chunk = -1
        decoded = []
        for index in chosen:
            chunk_index, row_index = divmod(index, BARCODE_CHUNK_ROWS)
            if chunk_index != last_chunk:
                decoded = orjson.loads(zlib.decompress(self.chunks[chunk_index]))
                last_chunk = chunk_index
            items.append(decoded[row_index])
        return {"items": items, "total": len(indices), "page": page, "page_size": page_size,
                "totals": orjson.loads(self.totals)}


class WarehouseInventoryCache:
    def __init__(self):
        self._condition = Condition()
        self._entries: OrderedDict[tuple, tuple[float, InventoryGroups | CompressedInventoryGroups]] = OrderedDict()
        self._pending: set[tuple] = set()
        self._bytes = 0
        self._builders = BoundedSemaphore(2)

    def get_or_load(self, key: tuple, load: Callable[[], InventoryGroups | CompressedInventoryGroups | None]) -> InventoryGroups | CompressedInventoryGroups | None:
        with self._condition:
            while True:
                now = monotonic()
                for expired in [item for item, entry in self._entries.items() if entry[0] <= now]:
                    self._bytes -= self._entries.pop(expired)[1].size
                if key in self._entries:
                    self._entries.move_to_end(key)
                    return self._entries[key][1]
                if key not in self._pending:
                    self._pending.add(key)
                    break
                # A concurrent identical request shares the calculation.
                self._condition.wait(timeout=1)
        try:
            with self._builders:
                result = load()
            if result is not None:
                with self._condition:
                    while self._entries and (self._bytes + result.size > MAX_BYTES or len(self._entries) >= MAX_ENTRIES):
                        self._bytes -= self._entries.popitem(last=False)[1][1].size
                    self._entries[key] = (monotonic() + TTL_SECONDS, result)
                    self._bytes += result.size
            return result
        finally:
            with self._condition:
                self._pending.discard(key)
                self._condition.notify_all()
