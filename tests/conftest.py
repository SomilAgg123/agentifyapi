import os
import socket
import threading
import time

import pytest
import uvicorn

os.environ["AGENTIFYAPI_DESCRIBER"] = "template"  # deterministic, no network


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ServerThread:
    def __init__(self, app):
        self.port = free_port()
        self.server = uvicorn.Server(uvicorn.Config(app, port=self.port, log_level="warning", lifespan="on"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        while not self.server.started:
            time.sleep(0.02)
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(5)


@pytest.fixture
def serve():
    return ServerThread


@pytest.fixture
def registry(tmp_path):
    from agentifyapi.registry import Registry
    return Registry(str(tmp_path / "r.db"))
