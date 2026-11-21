from typing import Any, Protocol


class Repository(Protocol):
    """Contrato mínimo para repositorios. Sin persistencia implementada todavía."""

    async def get(self, identifier: str) -> Any | None: ...

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[Any]: ...

    async def save(self, entity: Any) -> Any: ...
