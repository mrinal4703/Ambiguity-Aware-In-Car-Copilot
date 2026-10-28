"""Deterministic, offline NLU (module 2).

Used (a) when no LLM key is configured, (b) as the fallback when the LLM output
fails validation, and (c) in tests and evaluation so results are reproducible.

Rewrite -> split into tasks -> match patterns -> emit weighted goal candidates.
Scores are *prior* plausibilities, not calibrated probabilities: module 3 does
the calibration and the context-based re-weighting.
"""
from __future__ import annotations

import re
from typing import Any

from module_1_simulator.world import LOCATIONS

from .schema import GoalCandidate, NLUResult, Task

# ------------------------------------------------------------------ gazetteer
ALIASES: dict[str, str] = {
    "airport": "airport", "home": "home", "my home": "home", "patia": "home",
    "office": "tech_park", "work": "tech_park", "tech park": "tech_park", "cybercity": "tech_park",
    "kiit": "kiit_square", "kiit square": "kiit_square", "infocity": "infocity",
    "chandaka": "chandaka", "jaydev vihar": "jaydev_vihar", "vani vihar": "vani_vihar",
    "acharya vihar": "acharya_vihar", "rasulgarh": "rasulgarh", "esplanade": "esplanade",
    "mall": "esplanade", "cuttack": "cuttack", "master canteen": "master_canteen",
    "khandagiri": "khandagiri", "old town": "old_town", "puri": "puri_junction",
    "nh16": "nh16_junction", "railway station": "master_canteen",
}
for _node, _loc in LOCATIONS.items():
    ALIASES.setdefault(_loc["name"].lower(), _node)

MEETING_REF = re.compile(r"\b(my |the )?(next )?(meeting|appointment|review)\b")
UNSUPPORTED = {
    r"massage": "seat_massage", r"sun ?roof": "sunroof", r"auto ?pilot|self[- ]driv|drive (the car )?for me": "autopilot",
    r"heated steering|steering (wheel )?heat": "heated_steering", r"seat heat|heat(ed)? (my |the )?seat": "seat_heating",
}
SPLIT = re.compile(r"\s*(?:,\s*(?:(?:and then|and also|and|then)\s+)?|\b(?:and then|and also|and|then)\s+)"
                   r"(?=(?:please\s+)?(?:tell|text|message|send|call|"
                   r"ring|remind|take|navigate|drive|go|turn|set|play|open|close|find|let|inform|notify|switch|"
                   r"make|book|add)\b)")
NUM = r"(-?\d+(?:\.\d+)?)"


def find_location(text: str) -> str | None:
    t = text.lower()
    for alias in sorted(ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return ALIASES[alias]
    return None


def _norm(text: str) -> str:
    t = text.strip().lower()
    t = t.replace("’", "'").replace("i'm", "i am").replace("it's", "it is").replace("a/c", "ac")
    t = re.sub(r"\b(um+|uh+|hey copilot|copilot|please|kindly)\b[,]?\s*", "", t)
    return re.sub(r"\s+", " ", t).strip(" .!?")


def _c(goal: str, score: float, why: str = "", **params: Any) -> GoalCandidate:
    return GoalCandidate(goal=goal, params=params, score=score, rationale=why)


def _message_parts(t: str) -> tuple[str | None, str | None]:
    """Extract (recipient, text) from 'tell X that Y' / 'message X saying Y' / 'let X know Y'."""
    m = (re.search(r"\b(?:tell|inform|notify)\s+(.+?)\s+(?:that\s+)?(i am|i will|i'll|i may|i might|we|my|the|"
                   r"to|it|i)\b(.*)$", t)
         or re.search(r"\blet\s+(.+?)\s+know\s+(?:that\s+)?(.*)$", t)
         or re.search(r"\b(?:send (?:a )?(?:message|text) to|message|text|send)\s+(.+?)\s+(?:saying|that|:)\s+(.*)$", t))
    if not m:
        m2 = re.search(r"\b(?:send (?:a )?(?:message|text) to|message|text)\s+(\w+(?: \w+)?)$", t)
        return (m2.group(1), None) if m2 else (None, None)
    groups = [g for g in m.groups() if g is not None]
    recipient = groups[0].strip()
    text = " ".join(g.strip() for g in groups[1:]).strip()
    return recipient, (text or None)


def _recipient_ref(name: str | None) -> str | None:
    if name is None:
        return None
    n = name.strip().lower()
    if n in {"them", "the organizer", "the organiser", "everyone", "the team", "the attendees", "people in the meeting"} \
            or MEETING_REF.search(n):
        return "@next_event_people"
    if n in {"him", "her"}:
        return None
    return n


def _first_person(text: str) -> str:
    text = text[0].upper() + text[1:] if text else text
    return re.sub(r"\bi\b", "I", text)


def parse_task(raw: str) -> Task:
    t = _norm(raw)
    cands: list[GoalCandidate] = []
    intent = "unknown"
    explicit = False
    urgency = "normal"
    constraints: dict[str, Any] = {}
    entities: dict[str, Any] = {}

    if re.search(r"\b(urgent|asap|quickly|hurry|running late|late)\b", t):
        urgency = "high"
    if re.search(r"\b(avoid(ing)?|no|without) (the )?tolls?\b", t):
        constraints["avoid_tolls"] = True
    if re.search(r"\b(fastest|quickest)\b", t):
        constraints["minimize_travel_time"] = True

    # 1. missing capabilities ------------------------------------------------
    for pat, feature in UNSUPPORTED.items():
        if re.search(pat, t):
            intent, explicit = "unsupported", True
            cands = [_c("unsupported", 1.0, "feature not in the car", feature=feature)]
            break

    # 2. video ---------------------------------------------------------------
    if not cands and re.search(r"\b(movie|video|netflix|youtube|film)\b", t):
        intent, explicit = "video", True
        title = re.sub(r"\s*on the (screen|display)$", "", re.sub(r".*\b(play|watch|put on|show)\b\s*(a |the |some )?", "", t)) or "video"
        cands = [_c("video", 1.0, "explicit video request", title=title)]

    # 3. messaging / calls ---------------------------------------------------
    if not cands and re.search(r"\b(tell|text|message|inform|notify|let .+ know|send)\b", t) \
            and not re.search(r"\b(send|tell) me\b", t):
        rec, body = _message_parts(t)
        intent, explicit = "send_message", True
        ref = _recipient_ref(rec)
        if body is None and re.search(r"\blate\b", t):
            body = "I may be late"
        entities["recipient_mention"] = rec
        cands = [_c("send_message", 1.0, "explicit messaging verb", recipient=ref,
                    text=_first_person(body) if body else None)]
    if not cands and re.search(r"\b(call|ring|phone|dial)\b", t) and not re.search(r"\bcalled\b", t):
        m = re.search(r"\b(?:call|ring|phone|dial)\s+(.+)$", t)
        rec = _recipient_ref(m.group(1)) if m else None
        intent, explicit = "call_contact", True
        cands = [_c("call_contact", 1.0, "explicit call verb", recipient=rec)]

    # 4. charging ------------------------------------------------------------
    if not cands and re.search(r"\b(charg(e|ing|er)|battery (is )?(low|dying|almost)|low (on )?(battery|charge)|"
                               r"out of (charge|battery)|ev station)\b", t):
        intent = "find_charging"
        explicit = bool(re.search(r"\b(take me|navigate|find|go|need|stop)\b", t))
        if MEETING_REF.search(t) and re.search(r"\b(near|close to|by|around|before)\b", t):
            near = "@next_event_location"
        else:
            loc = find_location(re.sub(r"charging station", "", t))
            near = loc or "@current_route"
        if re.search(r"\bbefore\b.*\b(meeting|appointment)\b", t):
            constraints["deadline"] = "@next_event_start"
        cands = [_c("find_charging", 1.0, "charging keywords", near=near)]

    # 5. climate / windows ---------------------------------------------------
    if not cands:
        m = re.search(rf"\b(?:set|make|change|put)\b.*\b(?:temperature|temp|ac|it)\b.*?(?:to|at)\s+{NUM}", t)
        d = re.search(rf"{NUM}\s*(?:degrees?|°)?\s*(colder|cooler|warmer|hotter|lower|higher)", t)
        if m:
            intent, explicit = "climate", True
            cands = [_c("climate", 1.0, "explicit temperature", on=True, temperature_c=float(m.group(1)))]
        elif d:
            sign = -1 if d.group(2) in {"colder", "cooler", "lower"} else 1
            intent, explicit = "climate", True
            cands = [_c("climate", 1.0, "relative temperature", on=True, delta_c=sign * float(d.group(1)))]
        elif re.search(r"\b(cooler|colder|warmer|hotter)\b", t):
            sign = -1 if re.search(r"\b(cooler|colder)\b", t) else 1
            intent, explicit = "climate", True
            cands = [_c("climate", 1.0, "relative temperature", on=True, delta_c=sign * 2.0)]
        elif re.search(r"\bturn (on|off) (the )?(ac|air ?con|climate)\b|\b(ac|air ?con) (on|off)\b", t):
            on = "off" not in t
            intent, explicit = "climate", True
            cands = [_c("climate", 1.0, "explicit AC switch", on=on)]
        elif re.search(r"\b(hot|warm|stuffy|boiling|sweating|humid)\b", t):
            intent = "climate"
            cands = [_c("climate", 0.65, "indirect: too hot", on=True, delta_c=-2.0),
                     _c("windows", 0.35, "indirect: let air in", position=30)]
        elif re.search(r"\b(cold|freezing|chilly)\b", t):
            intent = "climate"
            cands = [_c("climate", 0.75, "indirect: too cold", on=True, delta_c=2.0),
                     _c("windows", 0.25, "indirect: close windows", position=0)]
    if not cands and re.search(r"\bwindows?\b", t):
        intent, explicit = "windows", True
        if re.search(r"\b(close|shut|roll up)\b", t):
            pos = 0
        elif re.search(r"\b(fully|all the way|completely|wide)\b", t):
            pos = 100
        elif re.search(r"\b(crack|bit|little|slightly)\b", t):
            pos = 20
        else:
            pos = 50
        cands = [_c("windows", 1.0, "explicit windows", position=pos)]

    # 6. navigation ----------------------------------------------------------
    if not cands and re.search(r"\b(take me|navigate|drive( me)?|go|head|directions|route|get me)\b", t):
        intent = "navigate"
        explicit = True
        if MEETING_REF.search(t):
            dest = "@next_event_location"
        else:
            dest = find_location(t)
        if dest is None:
            entities["destination_mention"] = re.sub(r".*\b(to|towards)\b\s*", "", t)
        cands = [_c("navigate", 1.0, "navigation verb", destination=dest)]

    # 7. tea / food / stops (classic ambiguous requests) ---------------------
    if not cands and re.search(r"\b(tea|chai|coffee)\b", t):
        intent = "ambiguous_need"
        cands = [_c("find_poi", 0.55, "find a tea or coffee shop", category="cafe", near="@current_route"),
                 _c("find_poi", 0.25, "find a rest stop", category="rest_area", near="@current_route"),
                 _c("reminder", 0.15, "remind to get tea", text="Get tea", time=None),
                 _c("navigate", 0.05, "already-known destination", destination="@next_event_location")]
    if not cands and re.search(r"\b(somewhere to stop|a break|take a break|rest stop|stop somewhere|"
                               r"pull over|need to stop|place to stop)\b", t):
        intent = "ambiguous_need"
        cands = [_c("find_poi", 0.40, "rest area", category="rest_area", near="@current_route"),
                 _c("find_poi", 0.30, "cafe", category="cafe", near="@current_route"),
                 _c("find_charging", 0.30, "charging stop", near="@current_route")]
    if not cands and re.search(r"\b(hungry|snack|food|eat)\b", t):
        intent = "ambiguous_need"
        cands = [_c("find_poi", 0.7, "food", category="cafe", near="@current_route"),
                 _c("find_poi", 0.3, "highway food plaza", category="rest_area", near="@current_route")]
    if not cands:
        poi = next((c for k, c in {"pharmacy": "pharmacy", "chemist": "pharmacy", "hospital": "hospital",
                                    "cafe": "cafe", "rest area": "rest_area"}.items() if k in t), None)
        if poi:
            intent, explicit = "find_poi", True
            cands = [_c("find_poi", 1.0, "explicit POI", category=poi, near="@current_route")]

    # 8. reminders, media, information ----------------------------------------
    if not cands and re.search(r"\bremind me\b", t):
        m = re.search(r"remind me (?:to )?(.+?)(?: at (\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?$", t)
        intent, explicit = "reminder", True
        cands = [_c("reminder", 1.0, "explicit reminder", text=_first_person(m.group(1)) if m else "Reminder",
                    time=_clock(m.group(2)) if m and m.group(2) else None)]
    if not cands and re.search(r"\b(play|pause|stop|skip)\b.*\b(music|song|songs|radio|track|podcast|something)\b|"
                               r"^play\b", t):
        action = "pause" if re.search(r"\b(pause|stop)\b", t) else "play"
        q = re.sub(r"^.*?\bplay\b\s*(some )?", "", t) if action == "play" else None
        intent, explicit = "media", True
        cands = [_c("media", 1.0, "explicit media", action=action, query=q or "music")]
    if not cands and re.search(r"\b(next|upcoming)\b.*\b(meeting|appointment|event)\b|\b(schedule|calendar)\b", t):
        intent, explicit = "info_calendar", True
        cands = [_c("info_calendar", 1.0, "calendar question")]
    if not cands and re.search(r"\b(battery|range|how far can)\b", t):
        intent, explicit = "info_vehicle", True
        cands = [_c("info_vehicle", 1.0, "vehicle question")]

    missing = [p for c in cands for p, v in c.params.items() if v is None and p not in {"time"}]
    requires_context = any(isinstance(v, str) and v.startswith("@") for c in cands for v in c.params.values()) \
        or len(cands) > 1 or bool(missing)
    return Task(text=raw.strip(), rewritten=_rewrite(intent, cands, t), intent=intent, candidates=cands,
                entities=entities, constraints=constraints, urgency=urgency, explicit_action=explicit,
                requires_context=requires_context, missing_params=sorted(set(missing)))


def _clock(s: str) -> str:
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s.strip())
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and h < 12:
        h += 12
    elif m.group(3) == "am" and h == 12:
        h = 0
    elif m.group(3) is None and 1 <= h <= 7:
        h += 12          # "at 6" while driving means the evening
    return f"{h:02d}:{mi:02d}"


def _rewrite(intent: str, cands: list[GoalCandidate], t: str) -> str:
    if not cands:
        return f"Unclear request: '{t}'"
    if len(cands) > 1:
        return "Ambiguous request; possible tasks: " + "; ".join(c.rationale for c in cands)
    c = cands[0]
    p = {k: v for k, v in c.params.items() if v is not None}
    return f"{c.goal}({', '.join(f'{k}={v}' for k, v in p.items())})"


def split_tasks(utterance: str) -> list[str]:
    parts = [p for p in SPLIT.split(_norm(utterance)) if p and p.strip()]
    return parts or [utterance]


class RuleBasedParser:
    name = "rules"

    def parse(self, utterance: str, history: list[dict] | None = None,
              vehicle_context: dict | None = None) -> NLUResult:
        tasks = [parse_task(p) for p in split_tasks(utterance)]
        known = [t for t in tasks if t.candidates]
        tasks = known or tasks[:1]
        conf = 0.9 if known and all(len(t.candidates) == 1 for t in known) else (0.6 if known else 0.1)
        return NLUResult(utterance=utterance, tasks=tasks, parser=self.name, confidence=conf)


YES = re.compile(r"^(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|confirm|correct|right|send it|"
                 r"sounds good|alright)\b")
NO = re.compile(r"^(no|nope|nah|cancel|don't|do not|stop|never ?mind|not now|abort)\b")


def classify_confirmation(text: str) -> bool | None:
    """True = yes, False = no, None = neither (treat as a new request)."""
    t = _norm(text)
    if NO.search(t):
        return False
    if YES.search(t):
        return True
    return None
