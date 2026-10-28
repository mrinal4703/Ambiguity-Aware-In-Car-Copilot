
from collections import defaultdict, deque
from typing import Any


class ContextManager:
    def __init__(self, max_history: int = 10):
        self.histories = defaultdict(
            lambda: deque(maxlen=max_history)
        )
        self.vehicle_states = defaultdict(dict)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ):
        self.histories[session_id].append({
            "role": role,
            "content": content
        })

    def get_history(self, session_id: str):
        return list(self.histories[session_id])

    def update_vehicle_context(
        self,
        session_id: str,
        context: dict
    ):
        self.vehicle_states[session_id].update(context)

    def get_vehicle_context(self, session_id: str):
        return self.vehicle_states[session_id].copy()
