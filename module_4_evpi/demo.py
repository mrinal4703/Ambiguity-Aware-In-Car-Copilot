"""Run:  python -m module_4_evpi.demo   (from the repo root)

Probabilities below are HYPOTHETICAL (taken from the project PDF's tea example).
"""
from contracts import BeliefState, Candidate

from .clarifier import EVPIClarifier, belief_features


def tea_scenario() -> None:
    print("=== 'I need some tea before the meeting' ===")
    belief = BeliefState(candidates=[
        Candidate(id="a", tool="find_tea_shop", prob=0.55),
        Candidate(id="b", tool="find_rest_stop", prob=0.25),
        Candidate(id="c", tool="add_reminder", prob=0.15),
        Candidate(id="d", tool="navigate_known_destination", prob=0.05),
    ])
    clar = EVPIClarifier()
    history = clar.new_history()
    print("features:", {k: round(v, 2) for k, v in belief_features(belief, history).items()})
    decision = clar.decide(belief, history)
    print(decision.kind.value, "->", decision.question, "|", decision.reason)
    belief, history, ok = clar.apply_answer(belief, history, decision.parameter, "find_tea_shop")
    decision = clar.decide(belief, history)
    print(decision.kind.value, "->", decision.candidate_id, "|", decision.reason)


def late_message_scenario() -> None:
    print("\n=== 'Tell them I may be late' (recipient ambiguous) ===")
    belief = BeliefState(candidates=[
        Candidate(id="a", tool="send_message", params={"recipient": "Priya (organizer)"}, prob=0.45),
        Candidate(id="b", tool="send_message", params={"recipient": "Rahul (colleague)"}, prob=0.40),
        Candidate(id="c", tool="send_message", params={"recipient": "Anita"}, prob=0.15),
    ])
    clar = EVPIClarifier()
    history = clar.new_history()

    print("-- if the calendar can resolve the recipient:")
    d = clar.decide(belief, history, resolvable_params={"recipient"})
    print(d.kind.value, "->", d.parameter, "|", d.reason)
    resolved, _ = clar.apply_context(belief, "recipient", "Priya (organizer)")
    print(clar.decide(resolved, history).kind.value)

    print("-- if it cannot, ask:")
    d = clar.decide(belief, history)
    print(d.kind.value, "->", d.question)


if __name__ == "__main__":
    tea_scenario()
    late_message_scenario()
