# Frontend: copilot dashboard   (module 10, owner: Souymadeep)

React + Vite dashboard with two tabs:

- **Integrated copilot**: talks to the module 10 API (`module_10_integration/api.py`). Shows the conversation
  (questions, confirmations with Yes/No buttons, blocked / deferred / refused replies), the candidate
  interpretations with probabilities, the plan, the tool calls, the safety verdict, the vehicle state and a map with
  the road network, charging stations (green available, red unavailable), the car and the active route.
  A scenario preset (default, low_battery, storm, highway, ...) and a configuration (full_fixed, full_rl, ablations)
  can be chosen and reset at any time.
- **LLM NLU demo**: the earlier page for the `module_2_nlu/llm_connection/` backend (port 8000).

## Run
Needs Node.js 22 LTS (or 20.19+). On older Node, `npm run dev` fails with "Cannot find native binding": update Node,
then delete `node_modules` and run `npm install` again.

```bash
# terminal 1, repository root
pip install -r requirements-dev.txt
uvicorn module_10_integration.api:app --port 8001

# terminal 2
cd module_10_integration/frontend
npm install
npm run dev            # http://localhost:5173
```
Set `VITE_COPILOT_API` to point at a different API URL. `npm run build` produces `dist/`.
