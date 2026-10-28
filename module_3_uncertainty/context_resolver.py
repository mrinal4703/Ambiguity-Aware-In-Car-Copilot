"""Internal context retrieval for uncertain parameters (module 3).

Before anyone asks the driver a question, references produced by the NLU
("@next_event_location", "@next_event_people", "@current_route", a bare first
name like "rahul") are looked up with *read-only* simulator tools. Every lookup
is a real tool call, so it appears in the environment log (ReAct observation).

A reference can resolve to
  * exactly one value   -> substituted directly (internal disambiguation),
  * several values      -> each becomes a weighted alternative (the belief splits),
  * nothing             -> the parameter stays None (missing; must be asked).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol


class ToolCaller(Protocol):
    def call(self, tool: str, **params: Any): ...


@dataclass
class Alternative:
    value: Any
    weight: float
    label: str = ""


@dataclass
class ContextLog:
    tool: str
    params: dict[str, Any]
    ok: bool
    summary: str


@dataclass
class ContextResolver:
    env: ToolCaller
    log: list[ContextLog] = field(default_factory=list)
    _cache: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------- lookups
    def _call(self, tool: str, **params: Any):
        key = f"{tool}:{sorted(params.items())}"
        if key in self._cache:
            return self._cache[key]
        r = self.env.call(tool, **params)
        n = len(r.data) if r.ok and isinstance(r.data, list) else None
        self.log.append(ContextLog(tool, params, r.ok, r.error or (f"{n} result(s)" if n is not None else "ok")))
        self._cache[key] = r
        return r

    def next_event(self) -> dict[str, Any] | None:
        r = self._call("get_calendar_events", next_only=True)
        return r.data[0] if r.ok and r.data else None

    def contacts(self, query: str | None = None) -> list[dict[str, Any]]:
        r = self._call("get_contacts", **({"query": query} if query else {}))
        return r.data if r.ok else []

    def vehicle(self) -> dict[str, Any]:
        r = self._call("get_vehicle_state")
        return r.data if r.ok else {}

    def driving(self) -> dict[str, Any]:
        r = self._call("get_driving_context")
        return r.data if r.ok else {}

    def current_route_anchor(self) -> str:
        nav = getattr(self.env, "navigation", None) or {}
        if nav.get("active") and nav.get("destination"):
            return nav["destination"]
        return self.vehicle().get("location", "home")

    # ------------------------------------------------------------ resolving
    def resolve(self, param: str, value: Any, task_text: str = "") -> list[Alternative] | None:
        """Return alternatives for a parameter value, or None if it needs no resolution."""
        if not isinstance(value, str):
            return None
        if value == "@next_event_location":
            ev = self.next_event()
            return [Alternative(ev["location"], 1.0, ev.get("location_name", ev["location"]))] if ev else []
        if value == "@current_route":
            return [Alternative(self.current_route_anchor(), 1.0, "current route")]
        if value == "@next_event_start":
            ev = self.next_event()
            return [Alternative(ev["start"], 1.0, ev["start"])] if ev else []
        if param == "recipient":
            return self._resolve_recipient(value)
        return None

    def _resolve_recipient(self, value: str) -> list[Alternative]:
        if value == "@next_event_people":
            ev = self.next_event()
            if not ev:
                return []
            people = [ev["organizer"]] + [a for a in ev["attendees"] if a != ev["organizer"]]
            weights = [0.55] + [0.45 / max(1, len(people) - 1)] * (len(people) - 1)
            by_id = {c["id"]: c for c in self.contacts()}
            return [Alternative(pid, w, self._label(by_id.get(pid), pid, ev, organizer=(pid == ev["organizer"])))
                    for pid, w in zip(people, weights) if pid in by_id]
        value = re.sub(r"^(?:to\s+)?(?:my|the|our)\s+", "", value.strip(), flags=re.I)
        matches = self.contacts(value)
        if not matches:
            return []
        if len(matches) == 1:
            return [Alternative(matches[0]["id"], 1.0, matches[0]["name"])]
        # Several contacts share the name: prior favours people in today's next meeting.
        ev = self.next_event()
        attendees = set(ev["attendees"]) if ev else set()
        raw = [(c, 1.2 if c["id"] in attendees else 1.0) for c in matches]
        return [Alternative(c["id"], w, self._label(c, c["id"], ev)) for c, w in raw]

    @staticmethod
    def _label(contact: dict | None, pid: str, ev: dict | None, organizer: bool = False) -> str:
        if contact is None:
            return pid
        rel = "organizer" if organizer else contact.get("relation", "")
        return f"{contact['name']} ({rel})" if rel else contact["name"]

    # ----------------------------------------------- resolvable-by-context
    def lookup(self, param: str, candidates: list[dict[str, Any]], task_text: str = "") -> Any | None:
        """Try to pick one value for `param` from context alone (used for GATHER_CONTEXT).

        Recipient rule: if the message is about timing (late / on my way / minutes) and exactly
        one of the candidate recipients attends the next calendar event, that person is meant.
        """
        if param == "recipient" and re.search(r"\b(late|on my way|minutes|running|delayed|reach)\b",
                                              task_text.lower()):
            ev = self.next_event()
            if ev:
                inside = [v for v in {c.get("recipient") for c in candidates} if v in ev["attendees"]]
                if len(inside) == 1:
                    return inside[0]
        return None

    def can_lookup(self, param: str, candidates: list[dict[str, Any]], task_text: str = "") -> bool:
        return self.lookup(param, candidates, task_text) is not None
