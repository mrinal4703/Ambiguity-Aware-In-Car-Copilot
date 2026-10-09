import { useState } from "react";
import RouteMap from "./RouteMap";
import "./App.css";

const API_BASE = "http://localhost:8000";

function App() {
  const [sessionId] = useState(() => crypto.randomUUID());

  const [trip, setTrip] = useState({
    origin: "",
    destination: "",
    current_location: "",
    battery_percent: 30,
    estimated_range_km: 100,
  });

  const [tripSaved, setTripSaved] = useState(false);
  const [savingTrip, setSavingTrip] = useState(false);

  const [utterance, setUtterance] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tripMessage, setTripMessage] = useState("");

  const updateTrip = (field, value) => {
    setTrip((previous) => ({
      ...previous,
      [field]: value,
    }));

    // Changing trip details requires saving the trip again.
    setTripSaved(false);
    setTripMessage("");
  };

  // Save the trip once before sending driver commands.
  const saveTrip = async (e) => {
    e.preventDefault();

    setSavingTrip(true);
    setError("");
    setTripMessage("");
    setResult(null);

    try {
      const response = await fetch(`${API_BASE}/trip`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          origin: trip.origin.trim(),
          destination: trip.destination.trim(),
          current_location: trip.current_location.trim(),
          battery_percent: Number(trip.battery_percent),
          estimated_range_km: Number(trip.estimated_range_km),
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail || data)
        );
      }

      setTripSaved(true);
      setTripMessage("Trip saved. You can now send driver commands.");
    } catch (err) {
      setError(err.message || "Could not save trip.");
    } finally {
      setSavingTrip(false);
    }
  };

  // Send only the driver's utterance and session ID.
  const generateIntent = async (e) => {
    e.preventDefault();

    if (!utterance.trim()) return;

    if (!tripSaved) {
      setError("Please save your trip before sending a command.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch(`${API_BASE}/copilot`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          utterance: utterance.trim(),
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail || data)
        );
      }

      setResult(data);
    } catch (err) {
      setError(err.message || "Unable to reach the backend.");
    } finally {
      setLoading(false);
    }
  };

  const detectedIntent =
    result?.intent_result?.intent ??
    result?.intent?.intent ??
    result?.intent ??
    "Unknown";

  const confidence =
    result?.intent_result?.confidence ??
    result?.intent?.confidence;

  const examples = [
    "I'm running low on charge",
    "Find a charging station",
    "Make it cooler",
    "Play some music",
  ];

  return (
    <div className="app">
      <main className="container">
        <header className="header">
          <span className="eyebrow">
            AI-POWERED DRIVER ASSISTANT
          </span>
          <h1>In-Car Copilot</h1>
          <p>
            Set up your trip once. Then use natural language to
            request assistance while the copilot remembers your trip.
          </p>
        </header>

        {/* STEP 1: Configure and save the trip */}
        <section className="panel">
          <h2>1. Trip Setup</h2>
          <p>
            Enter the initial trip and simulated vehicle state.
            You do not need to enter these details for every command.
          </p>

          <form onSubmit={saveTrip}>
            <div className="trip-grid">
              <div className="field">
                <label htmlFor="origin">Trip Origin</label>
                <input
                  id="origin"
                  required
                  value={trip.origin}
                  placeholder="e.g. Origin"
                  onChange={(e) =>
                    updateTrip("origin", e.target.value)
                  }
                />
              </div>

              <div className="field">
                <label htmlFor="destination">Destination</label>
                <input
                  id="destination"
                  required
                  value={trip.destination}
                  placeholder="e.g. Destination"
                  onChange={(e) =>
                    updateTrip("destination", e.target.value)
                  }
                />
              </div>

              <div className="field">
                <label htmlFor="current-location">
                  Current Car Position
                </label>
                <input
                  id="current-location"
                  required
                  value={trip.current_location}
                  placeholder="e.g. Origin"
                  onChange={(e) =>
                    updateTrip("current_location", e.target.value)
                  }
                />
              </div>

              <div className="field">
                <label htmlFor="battery">Battery (%)</label>
                <input
                  id="battery"
                  type="number"
                  min="0"
                  max="100"
                  required
                  value={trip.battery_percent}
                  onChange={(e) =>
                    updateTrip("battery_percent", e.target.value)
                  }
                />
              </div>

              <div className="field">
                <label htmlFor="range">
                  Estimated Range (km)
                </label>
                <input
                  id="range"
                  type="number"
                  min="0.1"
                  step="any"
                  required
                  value={trip.estimated_range_km}
                  onChange={(e) =>
                    updateTrip("estimated_range_km", e.target.value)
                  }
                />
              </div>
            </div>

            <button
              type="submit"
              className="generate"
              disabled={savingTrip || loading}
            >
              {savingTrip
                ? "Saving Trip..."
                : tripSaved
                  ? "Save Trip Again"
                  : "Save Trip"}
            </button>
          </form>

          {tripSaved && (
            <p className="response-message" role="status">
              ✓ {tripMessage}
            </p>
          )}
        </section>

        {/* STEP 2: Send driver messages */}
        <form onSubmit={generateIntent} className="panel">
          <h2>2. Driver Command</h2>
          <p>
            {tripSaved
              ? "Your trip is saved. Type what you need."
              : "Save your trip first to enable driver commands."}
          </p>

          <label htmlFor="command">Message</label>
          <textarea
            id="command"
            placeholder="e.g. I'm running low on charge"
            value={utterance}
            onChange={(e) => setUtterance(e.target.value)}
            rows={4}
            disabled={!tripSaved || loading}
          />

          <div className="examples">
            {examples.map((command) => (
              <button
                key={command}
                type="button"
                className="example"
                disabled={!tripSaved || loading}
                onClick={() => setUtterance(command)}
              >
                {command}
              </button>
            ))}
          </div>

          <button
            type="submit"
            className="generate"
            disabled={!tripSaved || loading || !utterance.trim()}
          >
            {loading ? "Processing..." : "Send Command →"}
          </button>
        </form>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        {/* STEP 3: Show the copilot response and map */}
        {result && (
          <section className="panel output">
            <h2>Copilot Response</h2>

            <div className="summary">
              <div>
                <span>Status</span>
                <strong>{result.status ?? "Response received"}</strong>
              </div>

              <div>
                <span>Detected Intent</span>
                <strong>{String(detectedIntent)}</strong>
              </div>

              <div>
                <span>Confidence</span>
                <strong>
                  {typeof confidence === "number"
                    ? `${(confidence * 100).toFixed(1)}%`
                    : "N/A"}
                </strong>
              </div>
            </div>

            {result.message && (
              <p className="response-message">{result.message}</p>
            )}

            {result.question && (
              <div className="clarification">
                <h3>Clarification Required</h3>
                <p>{result.question}</p>
              </div>
            )}

            {result.status === "route_updated" && result.route && (
              <div className="route-section">
                <h3>Updated Route</h3>

                <div className="route-details">
                  <p>
                    <strong>From:</strong>{" "}
                    {result.route.origin ?? trip.current_location}
                  </p>
                  <p>
                    <strong>Charging stop:</strong>{" "}
                    {result.route.charging_station?.name ??
                      "Charging station"}
                  </p>
                  <p>
                    <strong>Destination:</strong>{" "}
                    {result.route.destination ?? trip.destination}
                  </p>

                  {typeof result.route.distance_km === "number" && (
                    <p>
                      <strong>Total distance:</strong>{" "}
                      {result.route.distance_km} km
                    </p>
                  )}

                  {typeof result.route.eta_minutes === "number" && (
                    <p>
                      <strong>Estimated time:</strong>{" "}
                      {result.route.eta_minutes} minutes
                    </p>
                  )}
                </div>

                <RouteMap route={result.route} />
              </div>
            )}

            <details>
              <summary>View structured response</summary>
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </details>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;