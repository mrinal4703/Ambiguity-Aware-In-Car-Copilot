"""HTTP API for the dashboard (module 10).

    uvicorn module_10_integration.api:app --port 8001 --reload

Endpoints
    GET  /health
    GET  /world                 locations, roads, charging stations, POIs (for the map)
    GET  /state                 vehicle / navigation / messages + agent stats and recent turns
    POST /chat   {message}      one driver utterance -> Turn
    POST /reset  {preset, config}
    GET  /configs, /presets, /scenarios
    POST /scenarios/{id}/run    run one scenario with the simulated user, return transcript
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from module_1_simulator.environment import CarEnvironment
from module_1_simulator.initial_states import PRESETS, make_state
from module_1_simulator import world

from .agent import CopilotAgent
from .config import ABLATIONS
from .metrics import run_trial
from .scenarios import SCENARIOS, by_id

app = FastAPI(title="Ambiguity-Aware In-Car Copilot", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_rl_cache: dict[str, Any] = {}


def _rl_agent():
    if "agent" not in _rl_cache:
        from module_8_rl.evaluate import train_agent
        _rl_cache["agent"] = train_agent(episodes=60000)
    return _rl_cache["agent"]


def _make_agent(preset: str = "default", config: str = "full_fixed") -> CopilotAgent:
    if preset not in PRESETS:
        raise HTTPException(400, f"unknown preset {preset!r}; choose from {sorted(PRESETS)}")
    if config not in ABLATIONS:
        raise HTTPException(400, f"unknown config {config!r}; choose from {sorted(ABLATIONS)}")
    cfg = ABLATIONS[config]
    rl = _rl_agent() if cfg.policy == "rl" else None
    agent = CopilotAgent(CarEnvironment(make_state(preset)), cfg, rl_agent=rl)
    agent.preset, agent.config_name = preset, config
    return agent


_session: dict[str, CopilotAgent] = {}


def _agent() -> CopilotAgent:
    if "agent" not in _session:
        _session["agent"] = _make_agent()
    return _session["agent"]


class ChatIn(BaseModel):
    message: str


class ResetIn(BaseModel):
    preset: str = "default"
    config: str = "full_fixed"


def _state(agent: CopilotAgent) -> dict[str, Any]:
    st = agent.state()
    st["preset"] = getattr(agent, "preset", "default")
    st["config_name"] = getattr(agent, "config_name", "full_fixed")
    return st


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/world")
def get_world() -> dict[str, Any]:
    roads = [{"a": a, "b": b, "road_type": rt, "speed_kmh": sp, "toll": toll} for a, b, rt, sp, toll in world._ROADS]
    return {"locations": world.LOCATIONS, "roads": roads, "stations": world.CHARGING_STATIONS, "pois": world.POIS}


@app.get("/state")
def get_state() -> dict[str, Any]:
    return _state(_agent())


@app.post("/chat")
def chat(body: ChatIn) -> dict[str, Any]:
    msg = body.message.strip()
    if not msg:
        raise HTTPException(400, "message is empty")
    agent = _agent()
    turn = agent.handle(msg)
    return {"turn": turn.to_dict(), "state": _state(agent)}


@app.post("/reset")
def reset(body: ResetIn) -> dict[str, Any]:
    _session["agent"] = _make_agent(body.preset, body.config)
    return _state(_session["agent"])


@app.get("/configs")
def configs() -> dict[str, Any]:
    return {k: v.__dict__ for k, v in ABLATIONS.items()}


@app.get("/presets")
def presets() -> list[str]:
    return sorted(PRESETS)


@app.get("/scenarios")
def scenarios() -> list[dict[str, Any]]:
    return [{"id": s.id, "category": s.category, "description": s.description, "utterances": s.utterances,
             "preset": s.preset} for s in SCENARIOS]


@app.post("/scenarios/{sid}/run")
def run_scenario(sid: str, config: str = "full_fixed", seed: int = 0) -> dict[str, Any]:
    try:
        sc = by_id(sid)
    except KeyError:
        raise HTTPException(404, f"unknown scenario {sid!r}") from None
    if config not in ABLATIONS:
        raise HTTPException(400, f"unknown config {config!r}")
    cfg = ABLATIONS[config]
    r = run_trial(sc, cfg, seed=seed, perturb=seed > 0, rl_agent=_rl_agent() if cfg.policy == "rl" else None)
    return {"scenario": sid, "config": config, "success": r.success, "questions": r.questions,
            "safety_violation": r.safety_violation, "transcript": [{"user": u, "copilot": c} for u, c in r.transcript]}
