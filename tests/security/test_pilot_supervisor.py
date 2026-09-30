import asyncio
from types import SimpleNamespace

import pytest

from agentic_product_ops.pilot import cli


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["worker", "server"])
async def test_combined_launcher_cleans_up_sibling_on_exit(monkeypatch, failure):
    stopped = []
    ready = asyncio.Event()

    class Server:
        should_exit = False

        def __init__(self, config):
            pass

        async def serve(self):
            ready.set()
            try:
                if failure == "server":
                    await asyncio.sleep(0)
                    return
                await asyncio.Event().wait()
            finally:
                stopped.append("server")

    async def worker(runtime):
        await ready.wait()
        try:
            if failure == "worker":
                raise ValueError("worker failed")
            await asyncio.Event().wait()
        finally:
            stopped.append("worker")

    monkeypatch.setattr(cli.uvicorn, "Server", Server)
    monkeypatch.setattr(cli, "worker", worker)
    runtime = SimpleNamespace(
        settings=SimpleNamespace(
            api_port=18009,
            documentation_capability=None,
            delivery_specification_ids=(),
        ),
        app=lambda: object(),
    )
    if failure == "worker":
        with pytest.raises(ValueError, match="worker failed"):
            await cli.run(runtime)
    else:
        await cli.run(runtime)
    assert set(stopped) == {"server", "worker"}
