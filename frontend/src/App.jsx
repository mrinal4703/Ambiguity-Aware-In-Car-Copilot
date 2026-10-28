import { useState } from "react";
import Copilot from "./Copilot";
import NluDemo from "./NluDemo";
import "./copilot.css";

export default function App() {
  const [tab, setTab] = useState("copilot");
  return (
    <div className="shell">
      <nav className="tabs">
        <strong>Ambiguity-Aware In-Car Copilot</strong>
        <button className={tab === "copilot" ? "on" : ""} onClick={() => setTab("copilot")}>
          Integrated copilot
        </button>
        <button className={tab === "nlu" ? "on" : ""} onClick={() => setTab("nlu")}>
          LLM NLU demo
        </button>
      </nav>
      {tab === "copilot" ? <Copilot /> : <NluDemo />}
    </div>
  );
}
