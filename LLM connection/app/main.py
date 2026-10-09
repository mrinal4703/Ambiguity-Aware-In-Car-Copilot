import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.context_manager import ContextManager
from app.intent_parser import IntentParser
from app.orchestrator import CopilotOrchestrator


# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# FastAPI application
app = FastAPI(
    title="In-Vehicle NLU Intent Interpreter",
    description="Context-aware intent interpretation and orchestration",
    version="1.2.0",
)


# CORS: allow the React/Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize modules
context_manager = ContextManager()
intent_parser = IntentParser()
copilot_orchestrator = CopilotOrchestrator()


# Request schemas
class NLURequest(BaseModel):
    session_id: str = Field(min_length=1)
    utterance: str = Field(min_length=1, max_length=2000)
    vehicle_context: dict = Field(default_factory=dict)


class CopilotRequest(BaseModel):
    session_id: str = Field(min_length=1)
    utterance: str = Field(min_length=1, max_length=2000)
    vehicle_context: dict = Field(default_factory=dict)


class TripSetupRequest(BaseModel):
    session_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    current_location: str = Field(min_length=1)
    battery_percent: float = Field(ge=0, le=100)
    estimated_range_km: float = Field(gt=0)


# Health check
@app.get("/")
def home():
    return {
        "message": "In-Vehicle Copilot API is running",
        "endpoints": [
            "/trip",
            "/nlu/parse",
            "/copilot",
        ],
    }


# Retrieve conversation history and vehicle context
def get_request_context(
    session_id: str,
    new_vehicle_context: dict | None = None,
):
    history = context_manager.get_history(session_id)

    vehicle_context = context_manager.get_vehicle_context(
        session_id
    )

    vehicle_context.update(new_vehicle_context or {})

    return history, vehicle_context


# Store conversation history and vehicle context
def save_interaction(
    session_id: str,
    utterance: str,
    result: dict,
    vehicle_context: dict,
):
    context_manager.add_message(
        session_id,
        "user",
        utterance,
    )

    context_manager.add_message(
        session_id,
        "assistant",
        json.dumps(result),
    )

    context_manager.update_vehicle_context(
        session_id,
        vehicle_context,
    )


# Configure a trip once before sending driver commands
@app.post("/trip")
def setup_trip(request: TripSetupRequest):
    try:
        vehicle_context = {
            "origin": request.origin.strip(),
            "destination": request.destination.strip(),
            "current_location": request.current_location.strip(),
            "battery_percent": request.battery_percent,
            "estimated_range_km": request.estimated_range_km,
        }

        if not all(
            [
                vehicle_context["origin"],
                vehicle_context["destination"],
                vehicle_context["current_location"],
            ]
        ):
            raise HTTPException(
                status_code=422,
                detail="Origin, destination and current location are required.",
            )

        context_manager.update_vehicle_context(
            request.session_id,
            vehicle_context,
        )

        logger.info(
            "Trip configured for session %s",
            request.session_id,
        )

        return {
            "status": "trip_saved",
            "message": "Trip setup saved successfully.",
            "vehicle_context": vehicle_context,
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to save trip")
        raise HTTPException(
            status_code=500,
            detail="Could not save trip setup.",
        )


# Existing NLU endpoint
@app.post("/nlu/parse")
def parse_intent(request: NLURequest):
    try:
        history, vehicle_context = get_request_context(
            session_id=request.session_id,
            new_vehicle_context=request.vehicle_context,
        )

        result = intent_parser.parse(
            utterance=request.utterance,
            history=history,
            vehicle_context=vehicle_context,
        )

        save_interaction(
            session_id=request.session_id,
            utterance=request.utterance,
            result=result,
            vehicle_context=vehicle_context,
        )

        logger.info(
            "NLU request processed for session %s",
            request.session_id,
        )

        return result

    except ValueError as error:
        logger.exception("NLU parsing or validation error")
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )

    except Exception:
        logger.exception("Unexpected NLU error")
        raise HTTPException(
            status_code=500,
            detail="An internal NLU error occurred",
        )


# Copilot endpoint: use the saved trip for driver commands
@app.post("/copilot")
def process_copilot_request(request: CopilotRequest):
    try:
        history, vehicle_context = get_request_context(
            session_id=request.session_id,
            new_vehicle_context=request.vehicle_context,
        )

        # Do not allow an ordinary command to silently erase
        # previously saved trip details with empty values.
        result = copilot_orchestrator.process(
            utterance=request.utterance,
            history=history,
            vehicle_context=vehicle_context,
        )

        save_interaction(
            session_id=request.session_id,
            utterance=request.utterance,
            result=result,
            vehicle_context=vehicle_context,
        )

        logger.info(
            "Copilot request processed for session %s",
            request.session_id,
        )

        return result

    except ValueError as error:
        logger.exception("Copilot processing or validation error")
        raise HTTPException(
            status_code=422,
            detail=str(error),
        )

    except Exception:
        logger.exception("Unexpected Copilot error")
        raise HTTPException(
            status_code=500,
            detail="An internal Copilot error occurred",
        )