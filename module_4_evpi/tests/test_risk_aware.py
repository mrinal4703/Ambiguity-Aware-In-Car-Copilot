from contracts import BeliefState, Candidate, DecisionKind
from module_4_evpi import EVPIClarifier, risk_of


def _belief(tool, p, param="recipient"):
    return BeliefState(candidates=[
        Candidate(id="a", tool=tool, params={param: "A"}, prob=p, label="A"),
        Candidate(id="b", tool=tool, params={param: "B"}, prob=1 - p, label="B"),
    ])


def test_high_risk_asks_where_low_risk_proceeds():
    clar = EVPIClarifier()
    h = clar.new_history()
    assert risk_of(_belief("send_message", .85)) == "high"
    assert clar.decide(_belief("send_message", .85), h, risk="auto").kind == DecisionKind.ASK
    assert clar.decide(_belief("climate", .70, "temperature"), h, risk="auto").kind == DecisionKind.PROCEED


def test_high_question_cost_suppresses_low_value_questions():
    clar = EVPIClarifier()
    h = clar.new_history()
    b = _belief("find_cafe", .70, "name")
    assert clar.decide(b, h, risk="auto", question_cost=0.0).kind == DecisionKind.ASK
    assert clar.decide(b, h, risk="auto", question_cost=0.9).kind == DecisionKind.PROCEED


def test_default_behaviour_unchanged_without_risk():
    clar = EVPIClarifier()
    assert clar.decide(_belief("send_message", .85), clar.new_history()).kind == DecisionKind.PROCEED
