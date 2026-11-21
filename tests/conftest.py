import pytest

from agent_support_resolution.graph import SupportPipeline


@pytest.fixture()
def pipeline(tmp_path):
    return SupportPipeline(tmp_path / "work")
