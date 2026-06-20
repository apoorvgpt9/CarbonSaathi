"""Minimal Server-Sent Events parser for the CarbonSaathi test suite."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_EVENT_PREFIX = "event: "
_DATA_PREFIX = "data: "


@dataclass(frozen=True)
class SSEEvent:
    """A single parsed Server-Sent Event.

    Attributes:
        event: The event name from the ``event:`` line.
        data: The decoded JSON object from the ``data:`` line.
    """

    event: str
    data: dict[str, Any]


def parse_sse(text: str) -> list[SSEEvent]:
    """Parse a raw SSE response body into a list of :class:`SSEEvent`.

    Blocks are separated by a blank line; within a block, the ``event:`` and
    ``data:`` lines are extracted.  Blocks lacking either line are skipped.

    Args:
        text: The full SSE response body.

    Returns:
        The parsed events, in stream order.
    """
    events: list[SSEEvent] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_name: str | None = None
        data_line: str | None = None
        for line in block.split("\n"):
            if line.startswith(_EVENT_PREFIX):
                event_name = line[len(_EVENT_PREFIX) :]
            elif line.startswith(_DATA_PREFIX):
                data_line = line[len(_DATA_PREFIX) :]
        if event_name is not None and data_line is not None:
            events.append(SSEEvent(event=event_name, data=json.loads(data_line)))
    return events
