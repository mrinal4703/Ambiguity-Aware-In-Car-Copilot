import { useEffect, useRef, useState } from "react";
import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip } from "react-leaflet";

const API = import.meta.env.VITE_COPILOT_API || "http://localhost:8001";

async function call(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
  return res.json();
}

const KIND_LABEL = {
  question: "Clarifying question",
  confirm: "Needs confirmation",
  done: "Done",
  blocked: "Blocked by safety policy",
  deferred: "Deferred",
  refused: "Not supported",
  failed: "Failed",
  answer: "Answer",
};

const EXAMPLES = [
  "Take me to a charging station near my next appointment, and tell them I may be late",
  "I'm tired",
  "I'm running late",
  "Turn on parking assist",
  "I need tea",
  "Take me to my next meeting and find a charger on the way",
  "Take me to Cuttack",
  "I'm feeling hot",
  "Message Rahul that I will be late",
  "Open the windows",
  "Give me a seat massage",
];

function WorldMap({ world, snapshot }) {
  if (!world) return <div className="map placeholder">Loading map…</div>;
  const ll = (c) => [c[1], c[0]];
  const loc = world.locations;
  const nav = snapshot?.navigation;
  const route = nav?.route?.geometry?.coordinates?.map(ll) || [];
  const here = loc[snapshot?.vehicle?.location]?.coords;
  const waypoints = new Set(nav?.waypoints || []);
  const live = Object.fromEntries((snapshot?.stations || []).map((s) => [s.id, s.available]));
  const closed = new Set((snapshot?.closed_roads || []).map(([a, b]) => [a, b].sort().join("|")));
  return (
    <MapContainer className="map" center={[20.32, 85.83]} zoom={11} scrollWheelZoom={false}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {world.roads.map((r) => (
        <Polyline
          key={`${r.a}-${r.b}`}
          positions={[ll(loc[r.a].coords), ll(loc[r.b].coords)]}
          pathOptions={closed.has([r.a, r.b].sort().join("|"))
            ? { color: "#b91c1c", weight: 4 }
            : { color: r.toll ? "#b45309" : "#94a3b8", weight: 2, dashArray: r.toll ? "6 4" : null }}
        />
      ))}
      {route.length > 0 && <Polyline positions={route} pathOptions={{ color: "#2563eb", weight: 6 }} />}
      {world.stations.map((s) => (
        <CircleMarker
          key={s.id}
          center={ll(loc[s.node].coords)}
          radius={waypoints.has(s.id) ? 10 : 6}
          pathOptions={{ color: (live[s.id] ?? s.available) ? "#15803d" : "#b91c1c", fillOpacity: 0.85 }}
        >
          <Popup>
            <b>{s.name}</b>
            <br />
            {s.power_kw} kW · {s.connectors.join(", ")} · {s.available ? "available" : "unavailable"}
          </Popup>
        </CircleMarker>
      ))}
      {here && (
        <CircleMarker center={ll(here)} radius={9} pathOptions={{ color: "#111827", fillColor: "#facc15", fillOpacity: 1 }}>
          <Tooltip permanent direction="top">Car</Tooltip>
        </CircleMarker>
      )}
      {nav?.destination && loc[nav.destination] && (
        <CircleMarker center={ll(loc[nav.destination].coords)} radius={9} pathOptions={{ color: "#1d4ed8", fillOpacity: 1 }}>
          <Tooltip permanent direction="top">{loc[nav.destination].name}</Tooltip>
        </CircleMarker>
      )}
    </MapContainer>
  );
}

function Vehicle({ snapshot, stats }) {
  if (!snapshot) return null;
  const v = snapshot.vehicle;
  const d = snapshot.driving;
  const n = snapshot.navigation;
  return (
    <div className="card">
      <h3>Vehicle</h3>
      <dl className="kv">
        <dt>Battery</dt><dd>{v.battery_pct.toFixed(0)}% ({v.range_km} km range)</dd>
        <dt>Speed</dt><dd>{v.speed_kmh} km/h · {d.road_type}</dd>
        <dt>Weather</dt><dd>{d.weather}, {d.outside_temperature_c}°C outside</dd>
        <dt>Cabin</dt><dd>{v.cabin_temperature_c}°C · AC {v.ac.on ? `on ${v.ac.temperature_c}°C` : "off"}</dd>
        <dt>Time</dt><dd>{d.time}</dd>
        <dt>Navigation</dt>
        <dd>
          {n.active
            ? `${n.destination}${n.waypoints.length ? ` via ${n.waypoints.join(", ")}` : ""} · ${n.route?.distance_km} km`
            : "inactive"}
        </dd>
        <dt>Messages</dt><dd>{snapshot.messages_sent.length}</dd>
        <dt>Calls</dt><dd>{snapshot.calls.length}</dd>
        <dt>Reminders</dt><dd>{snapshot.reminders.length}</dd>
      </dl>
      {stats && (
        <p className="muted">
          questions {stats.questions} · context lookups {stats.context_lookups} · blocked {stats.blocked} ·
          deferred {stats.deferred}
        </p>
      )}
    </div>
  );
}

function Beliefs({ beliefs, difficulty, world }) {
  if (!beliefs) return null;
  const names = Object.fromEntries((world?.stations || []).map((s) => [s.id, s.name]));
  const avail = Object.entries(beliefs.station_availability || {}).sort((a, b) => a[1] - b[1]).slice(0, 4);
  const cf = beliefs.consumption_factor;
  const rt = beliefs.route_time_min;
  return (
    <div className="card">
      <h3>World beliefs</h3>
      <dl className="kv">
        <dt>Driving load</dt><dd>{difficulty}</dd>
        <dt>Energy use</dt><dd>{cf.mean.toFixed(2)} × model (± {cf.sd.toFixed(2)}, {cf.observations} obs)</dd>
        {rt && <><dt>Route time</dt><dd>{rt.mean.toFixed(0)} min (90%: {rt.p90.toFixed(0)} min)</dd></>}
        {beliefs.p_reach_destination !== undefined && (
          <><dt>P(arrive with reserve)</dt><dd>{(beliefs.p_reach_destination * 100).toFixed(0)}%</dd></>
        )}
      </dl>
      <h4>Least likely free chargers</h4>
      {avail.map(([id, p]) => (
        <div className="bar" key={id}>
          <span>{names[id] || id}</span>
          <div><i style={{ width: `${Math.round(p * 100)}%` }} /></div>
          <b>{(p * 100).toFixed(0)}%</b>
        </div>
      ))}
    </div>
  );
}

function Reasoning({ turn }) {
  if (!turn) return <div className="card muted">Send a request to see the copilot's reasoning.</div>;
  return (
    <div className="card">
      <h3>Reasoning for “{turn.user}”</h3>
      {turn.decision?.kind && (
        <p>
          <span className={`pill ${turn.decision.kind}`}>{turn.decision.kind}</span> {turn.decision.reason}
          {turn.decision.by && <span className="muted"> ({turn.decision.by})</span>}
        </p>
      )}
      {turn.candidates?.length > 0 && (
        <>
          <h4>Candidate interpretations</h4>
          {turn.candidates.map((c) => (
            <div className="bar" key={c.id}>
              <span>{c.label}</span>
              <div><i style={{ width: `${Math.round(c.prob * 100)}%` }} /></div>
              <b>{(c.prob * 100).toFixed(0)}%</b>
            </div>
          ))}
        </>
      )}
      {turn.plan?.length > 0 && (
        <>
          <h4>Plan</h4>
          <ol className="plan">
            {turn.plan.map((s) => (
              <li key={s.id}>
                <code>{s.action}</code> {Object.keys(s.params || {}).length > 0 && <span className="muted">{JSON.stringify(s.params)}</span>}
                {s.safety_class !== "low" && <span className="pill confirm">{s.safety_class}</span>}
              </li>
            ))}
          </ol>
        </>
      )}
      {turn.tool_calls?.length > 0 && (
        <>
          <h4>Tool calls</h4>
          <ul className="calls">
            {turn.tool_calls.map((c, i) => (
              <li key={i} className={c.ok ? "ok" : "bad"}>
                {c.ok ? "✓" : "✗"} <code>{c.tool}</code> {c.error && <span>— {c.error}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {turn.verdict && (
        <p className="muted">Safety gate: {turn.verdict.verdict}{turn.verdict.reason && ` — ${turn.verdict.reason}`}</p>
      )}
    </div>
  );
}

export default function Copilot() {
  const [world, setWorld] = useState(null);
  const [state, setState] = useState(null);
  const [turns, setTurns] = useState([]);
  const [message, setMessage] = useState("");
  const [preset, setPreset] = useState("default");
  const [config, setConfig] = useState("full_fixed");
  const [presets, setPresets] = useState(["default"]);
  const [configs, setConfigs] = useState(["full_fixed"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottom = useRef(null);

  useEffect(() => {
    Promise.all([call("/world"), call("/state"), call("/presets"), call("/configs")])
      .then(([w, s, p, c]) => {
        setWorld(w);
        setState(s);
        setPresets(p);
        setConfigs(Object.keys(c));
      })
      .catch((e) => setError(`Cannot reach the copilot API at ${API} (${e.message}). Start it with: uvicorn module_10_integration.api:app --port 8001`));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns]);

  const send = async (text) => {
    const msg = (text ?? message).trim();
    if (!msg || busy) return;
    setBusy(true);
    setError("");
    try {
      const r = await call("/chat", { message: msg });
      setTurns((t) => [...t, r.turn]);
      setState(r.state);
      setMessage("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const act = async (path, body) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const r = await call(path, body);
      setTurns((t) => [...t, r.turn]);
      setState(r.state);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const nav = state?.snapshot?.navigation;
  const closeRoad = () => {
    const p = nav?.route?.path || [];
    if (p.length >= 2) act("/event", { kind: "road_closed", a: p[0], b: p[1] });
  };
  const stopOffline = () => {
    const stations = state?.snapshot?.stations || world?.stations || [];
    const st = nav?.waypoints?.find((w) => stations.some((s) => s.id === w)) ||
      stations.find((s) => s.node === nav?.destination)?.id;
    if (st) act("/event", { kind: "station_offline", station: st });
  };

  const reset = async () => {
    setBusy(true);
    setError("");
    try {
      setState(await call("/reset", { preset, config }));
      setTurns([]);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const last = turns[turns.length - 1];
  const pending = state?.pending;

  return (
    <main className="copilot">
      <section className="left">
        <div className="card controls">
          <label>
            Scenario state
            <select value={preset} onChange={(e) => setPreset(e.target.value)}>
              {presets.map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
          <label>
            Configuration
            <select value={config} onChange={(e) => setConfig(e.target.value)}>
              {configs.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <button onClick={reset} disabled={busy}>Reset</button>
        </div>
        <div className="card chat">
          {turns.length === 0 && <p className="muted">Try one of the examples below.</p>}
          {turns.map((t, i) => (
            <div key={i}>
              <div className="msg user">{t.user}</div>
              <div className={`msg bot ${t.kind}`}>
                <small>{KIND_LABEL[t.kind] || t.kind}</small>
                {t.reply}
              </div>
            </div>
          ))}
          <div ref={bottom} />
        </div>
        {pending && (
          <div className="quick">
            {pending === "confirm" ? (
              <>
                <button onClick={() => send("yes")}>Yes</button>
                <button onClick={() => send("no")}>No</button>
              </>
            ) : (
              <span className="muted">The copilot is waiting for your answer.</span>
            )}
          </div>
        )}
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Say something to the copilot…" />
          <button disabled={busy || !message.trim()}>{busy ? "…" : "Send"}</button>
        </form>
        <div className="examples">
          {EXAMPLES.map((x) => (
            <button key={x} onClick={() => send(x)} disabled={busy}>{x}</button>
          ))}
        </div>
        <div className="card trip">
          <h3>While driving</h3>
          <div className="examples">
            <button onClick={() => act("/drive", { minutes: 5 })} disabled={busy || !nav?.active}>Drive 5 min</button>
            <button onClick={() => act("/drive", { minutes: 20 })} disabled={busy || !nav?.active}>Drive 20 min</button>
            <button onClick={closeRoad} disabled={busy || !nav?.active}>Close a road on the route</button>
            <button onClick={stopOffline} disabled={busy || !nav?.active}>Charging stop goes offline</button>
            <button onClick={() => act("/event", { kind: "drain", factor: 1.8 })} disabled={busy}>Battery drains 1.8× faster</button>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
      </section>
      <section className="right">
        <WorldMap world={world} snapshot={state?.snapshot} />
        <div className="grid2">
          <Vehicle snapshot={state?.snapshot} stats={state?.stats} />
          <Reasoning turn={last} />
          <Beliefs beliefs={state?.beliefs} difficulty={state?.difficulty} world={world} />
        </div>
      </section>
    </main>
  );
}
