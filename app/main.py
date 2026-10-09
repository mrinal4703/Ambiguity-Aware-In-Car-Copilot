
import json
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.context_manager import ContextManager
from app.intent_parser import IntentParser


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="In-Vehicle NLU Intent Interpreter",
    description="Context-aware intent interpretation and rewriting",
    version="1.0.0"
)

context_manager = ContextManager()
intent_parser = IntentParser()


class NLURequest(BaseModel):
    session_id: str
    utterance: str = Field(min_length=1, max_length=2000)
    vehicle_context: dict = Field(default_factory=dict)


@app.get("/")
def home():
    return {
        "message": "NLU Intent Interpreter is running"
    }

def interpret_request(
    utterance: str,
    session_id: str,
    new_vehicle_context: dict | None = None
):
    history = context_manager.get_history(session_id)

    vehicle_context = context_manager.get_vehicle_context(
        session_id
    )

    vehicle_context.update(new_vehicle_context or {})

    result = intent_parser.parse(
        utterance=utterance,
        history=history,
        vehicle_context=vehicle_context
    )

    if hasattr(result, "model_dump"):
        result = result.model_dump()

    return result
@app.post("/nlu/parse")
def parse_intent(request: NLURequest):
    try:
        session_id = request.session_id

        result = interpret_request(
            utterance=request.utterance,
            session_id=session_id,
            new_vehicle_context=request.vehicle_context
        )

        context_manager.add_message(
            session_id,
            "user",
            request.utterance
        )

        context_manager.add_message(
            session_id,
            "assistant",
            json.dumps(result)
        )

        context_manager.update_vehicle_context(
            session_id,
            context_manager.get_vehicle_context(session_id)
        )

        return result

    except ValueError as error:
        logger.exception("NLU parsing error")
        raise HTTPException(status_code=422, detail=str(error))

    except Exception:
        logger.exception("Unexpected NLU error")
        raise HTTPException(
            status_code=500,
            detail="An internal NLU error occurred"
        )
