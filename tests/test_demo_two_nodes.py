"""Smoke test for the manual two-node demonstration."""

import pytest

from solora.demo_two_nodes import run_demo


def test_two_node_demo_completes(capsys: pytest.CaptureFixture[str]) -> None:
    run_demo()

    output = capsys.readouterr().out
    assert "Första sändningen tappades; outbox=1" in output
    assert "Retry levererad och COMMIT_ACK mottagen; outbox=0, inlägg på B=1" in output
    assert "Samma frame spelades upp igen; inlägg på B=1, deduplicerade=1" in output
