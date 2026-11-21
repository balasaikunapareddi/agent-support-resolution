from agent_support_resolution.demo import main as demo_main
from agent_support_resolution.evals import EVAL_CASES, main as evals_main, run_evals


def test_eval_set_has_twelve_cases():
    assert len(EVAL_CASES) == 12


def test_all_evals_pass():
    results = run_evals()
    failures = {r.name: r.failures for r in results if not r.passed}
    assert failures == {}


def test_evals_main_exit_zero(capsys):
    assert evals_main() == 0
    out = capsys.readouterr().out
    assert "12/12 eval cases passed" in out


def test_demo_main_runs(capsys):
    assert demo_main() == 0
    out = capsys.readouterr().out
    assert "human review queue" in out
    assert "audit trail for TKT-1004" in out
    assert "12/12 eval cases passed" in out
    assert "simulated sends" in out
