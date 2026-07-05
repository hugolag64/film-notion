from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional

from backend.core.processor import EnrichmentProcessor


@dataclass
class AppState:
    all_medias: List[Any] = field(default_factory=list)
    medias: List[Any] = field(default_factory=list)
    force: bool = False
    running: bool = False
    last_synced: Optional[str] = None


@dataclass
class AppContext:
    processor: EnrichmentProcessor
    state: AppState
    reload: Callable[[], Awaitable[None]]
    rerender: Callable[[], None]
    navigate: Callable[[str], None]
