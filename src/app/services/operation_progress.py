from __future__ import annotations

from collections.abc import Callable
from typing import Any


class OperationCancelled(RuntimeError):
    pass


class OperationProgress:
    def __init__(self, check: Callable[[], bool], update: Callable[..., None]):
        self._check = check
        self._update = update

    def checkpoint(self) -> None:
        if self._check():
            raise OperationCancelled("已取消；已完成的结果已保留。")

    def report(self, *, message: str = "", total: int | None = None, completed: int | None = None,
               item: dict[str, Any] | None = None) -> None:
        self._update(message=message, total=total, completed=completed, item=item)
