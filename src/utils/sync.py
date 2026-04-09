from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sync-asyncio")
    return _executor


def run_sync(awaitable: Awaitable[T]) -> T:
    """
    在同步代码（Streamlit）里安全运行 async awaitable。

    - **无事件循环**：直接 asyncio.run
    - **已有事件循环（例如某些运行环境）**：在后台线程创建新 loop 执行
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    # Running inside an event loop -> execute in a dedicated thread.
    def _runner() -> T:
        return asyncio.run(awaitable)

    fut: Future[T] = _get_executor().submit(_runner)
    return fut.result()


def syncify(fn: Callable[..., Awaitable[T]]) -> Callable[..., T]:
    """把 async 函数包装成同步函数（内部用 run_sync）。"""

    def _wrapped(*args: Any, **kwargs: Any) -> T:
        return run_sync(fn(*args, **kwargs))

    return _wrapped

