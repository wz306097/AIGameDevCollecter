from __future__ import annotations

from pathlib import Path
from typing import Protocol

from survey.models import Session, HarnessEvent


class HarnessAdapter(Protocol):
    def parse_transcript(self, path: Path) -> Session: ...
    def extract_events(self, path: Path) -> list[HarnessEvent]: ...
