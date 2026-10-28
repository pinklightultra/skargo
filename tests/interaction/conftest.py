"""One finished LOW TIDE folder for the outcome tests. Built once per session."""

import pytest

from examples.demo.desk.perform import click


@pytest.fixture(scope="session")
def finished(tmp_path_factory):
    root = tmp_path_factory.mktemp("finished")
    out = click(root, "stage:all")
    assert out["tone"] == "ok", out["summary"] + "\n" + out["detail"][-2500:]
    return root
