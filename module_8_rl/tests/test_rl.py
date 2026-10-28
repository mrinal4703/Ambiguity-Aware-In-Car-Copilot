import pytest

from contracts import BeliefState, Candidate
from module_8_rl import (Act, AlwaysExecute, DecisionEnv, HybridPolicy, QAgent, Situation, features,
                         gate_fallback, safety_mask)
from module_8_rl.evaluate import evaluate_policy, train_agent


def sit(probs, true="c0", **kw):
    b = BeliefState(candidates=[Candidate(id=f"c{i}", tool=f"g{i}", prob=p) for i, p in enumerate(probs)])
    return Situation(belief=b, true_id=true, **kw)


def test_rewards_follow_table():
    env = DecisionEnv(seed=0)
    assert env.step(Act.EXECUTE, sit([1.0])).reward == 10
    assert env.step(Act.EXECUTE, sit([0.6, 0.4], true="c1")).reward == -5
    assert env.step(Act.EXECUTE, sit([1.0], safety="forbidden")).reward == -20
    assert env.step(Act.CLARIFY, sit([0.5, 0.5])).reward == 2
    assert env.step(Act.CLARIFY, sit([1.0])).reward == -2
    assert env.step(Act.REFUSE, sit([1.0], safety="forbidden")).reward == 8
    assert env.step(Act.DELAY, sit([1.0], safety="deferrable")).reward == 8
    assert env.step(Act.SUGGEST_ALTERNATIVE, sit([1.0], supported=False)).reward == 8


def test_clarify_resolves_toward_truth_and_uses_budget():
    env = DecisionEnv(seed=1, answer_reliability=1.0)
    s = sit([0.6, 0.4], true="c1")
    env.step(Act.CLARIFY, s)
    assert s.top().id == "c1" and s.budget == 1 and s.questions == 1


def test_safety_mask_and_fallback():
    s = sit([1.0], safety="deferrable")
    assert not safety_mask(s)[Act.EXECUTE]
    assert gate_fallback(s) == Act.DELAY
    assert gate_fallback(sit([1.0], supported=False)) == Act.SUGGEST_ALTERNATIVE
    assert not safety_mask(sit([0.5, 0.5], budget=0))[Act.CLARIFY]


def test_features_are_discrete():
    f = features(sit([0.55, 0.45]))
    assert f == (1, 0, 2, 0, 1, 1, 0)


def test_agent_never_executes_masked_actions():
    ag = QAgent(seed=0, epsilon=1.0)
    s = sit([1.0], safety="forbidden")
    assert all(ag.act(s, explore=True) != Act.EXECUTE for _ in range(200))


@pytest.fixture(scope="module")
def agent():
    return train_agent(episodes=80000)


def test_q_learning_beats_always_execute_and_is_safe(agent):
    q = evaluate_policy(agent, episodes=1500)
    base = evaluate_policy(AlwaysExecute(), episodes=1500)
    assert q.reward > base.reward + 1.5
    assert q.gate_interventions == 0
    assert q.success > 0.95


def test_q_learning_competitive_with_hybrid(agent):
    q = evaluate_policy(agent, episodes=1500)
    h = evaluate_policy(HybridPolicy(), episodes=1500)
    assert q.reward >= h.reward - 0.5


def test_learned_policy_sensible_choices(agent):
    assert agent.decide(sit([1.0], safety="forbidden")) == Act.REFUSE
    assert agent.decide(sit([1.0], safety="deferrable")) == Act.DELAY
    assert agent.decide(sit([1.0], supported=False)) == Act.SUGGEST_ALTERNATIVE
    assert agent.decide(sit([0.97, 0.03])) == Act.EXECUTE
    assert agent.decide(sit([0.4, 0.35, 0.25])) in (Act.CLARIFY, Act.GATHER_CONTEXT)


def test_save_load(tmp_path, agent):
    p = tmp_path / "q.json"
    agent.save(p)
    ag2 = QAgent.load(p)
    s = sit([0.4, 0.35, 0.25])
    assert ag2.decide(s) == agent.decide(s)
