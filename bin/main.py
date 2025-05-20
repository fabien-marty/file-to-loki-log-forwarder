#!/usr/bin/env python3

from dataclasses import dataclass, field
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
import os
import signal
import subprocess
import threading
import time
from typing import Literal
import httpx
from jinja2 import Template
import stlog
from stlog.setup import _make_default_outputs
from stlog.output import RotatingFileOutput
from stlog.formatter import JsonFormatter, DEFAULT_STLOG_GCP_JSON_FORMAT

MANAGEMENT_API_PORT = int(os.environ.get("MANAGEMENT_API_PORT", "8952"))
LOGGER = stlog.getLogger("file-to-loki-log-forwarder")
ROTATING_FILE_OUTPUT = RotatingFileOutput(
    filename="/internal_logs/file-to-loki-log-forwarder.log",
    formatter=JsonFormatter(fmt=DEFAULT_STLOG_GCP_JSON_FORMAT),
    max_bytes=10 * 1024 * 1024,
    backup_count=3,
)


@dataclass
class VectorManager:
    __vector_process: subprocess.Popen | None = None
    __stop_requested: bool = False
    __state: Literal["IDLE", "STARTING", "UP", "STOPPING", "DOWN"] = "IDLE"
    __lock: threading.Lock = field(default_factory=threading.Lock)

    def request_stop(self):
        with self.__lock:
            self.__stop_requested = True

    @property
    def is_up(self) -> bool:
        with self.__lock:
            return self.__state == "UP"

    @property
    def is_stopping(self) -> bool:
        with self.__lock:
            return self.__state == "STOPPING"

    @property
    def is_down(self) -> bool:
        with self.__lock:
            return self.__state == "DOWN"

    @property
    def is_starting(self) -> bool:
        with self.__lock:
            return self.__state == "STARTING"

    def launch_and_wait(self, config: str):
        self.__state = "STARTING"
        self.__vector_process = subprocess.Popen(
            ["bin/vector", "--config-yaml", config],
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        while True:
            time.sleep(1)
            with self.__lock:
                if self.__state == "UP" and self.__stop_requested:
                    try:
                        LOGGER.info("Waiting 1s before sending SIGTERM to vector...")
                        ROTATING_FILE_OUTPUT._handler.flush()  # Let's flush this latest message (after that we have not guarantee that vector will see the next ones)
                        time.sleep(
                            1
                        )  # Wait 1s to be sure that vector saw the latest items in sources
                        self.__vector_process.terminate()  # send SIGTERM
                        self.__state = "STOPPING"
                        LOGGER.info("SIGTERM sent to vector")
                    except Exception:
                        pass
                return_code = self.__vector_process.poll()
                if return_code is not None:
                    LOGGER.info("Vector exited with code %s", return_code)
                    self.__state = "DOWN"
                    break
            if self.__state == "STARTING":
                healthy = self.is_healthy()
                with self.__lock:
                    if healthy:
                        LOGGER.info("Vector is up and healthy")
                        self.__state = "UP"

    def is_healthy(self) -> bool:
        res = False
        try:
            response = httpx.get("http://127.0.0.1:8686/health", timeout=1)
            res = response.status_code == 200
        except Exception:
            pass
        return res


VECTOR_MANAGER = VectorManager()


def is_debug() -> bool:
    return os.environ.get("DEBUG", "0").lower() == "1"


def error(*args, **kwargs):
    LOGGER.error(*args, **kwargs)
    if is_debug() and kwargs.get("stdout"):
        print("<DEBUG STDOUT>")
        print(kwargs["stdout"])
        print("</DEBUG STDOUT>")
    if is_debug() and kwargs.get("stderr"):
        print("<DEBUG STDERR>")
        print(kwargs["stderr"])
        print("</DEBUG STDERR>")


def die():
    LOGGER.error("Exiting...")
    exit(1)


def signal_handler(signum, frame):
    LOGGER.info("Received signal %s", signum)
    VECTOR_MANAGER.request_stop()


def generate_vector_config_from_env(source: str, destination: str):
    with open(source) as f:
        config_template = f.read()
    template = Template(config_template)
    rendered_config = template.render(os.environ)
    if is_debug():
        print("<DEBUG RENDERED CONFIG>")
        print(rendered_config)
        print("</DEBUG RENDERED CONFIG>")
    with open(destination, "w") as f:
        f.write(rendered_config)


def validate_vector_config(config: str) -> bool:
    try:
        cp = subprocess.run(
            [
                "bin/vector",
                "validate",
                "--skip-healthchecks",
                "--deny-warnings",
                "--config-yaml",
                config,
            ],
            capture_output=True,
        )
    except Exception:
        error("Can't launch vector to validate config", exc_info=True)
        return False
    if cp.returncode != 0:
        error(
            "Invalid vector config",
            exc_info=True,
            stdout=cp.stdout,
            stderr=cp.stderr,
        )
        return False
    return True


class HealthHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        if VECTOR_MANAGER.is_stopping:
            LOGGER.debug(
                "Vector is stopping, returning 200 for health check (to avoid premature kill)"
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"STOPPING")
        elif VECTOR_MANAGER.is_down:
            LOGGER.debug("Vector is down, returning 503 for health check")
            self.send_response(503)
            self.end_headers()
        elif VECTOR_MANAGER.is_starting:
            LOGGER.debug("Vector is starting, returning 503 for health check")
            self.send_response(503)
            self.end_headers()
        else:
            LOGGER.debug("Vector is healthy, returning 200 for health check")
            self.send_response(200)
            self.end_headers()

    def do_POST(self):
        if self.path not in ("/stop", "/stop_and_wait"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return
        LOGGER.info("Received stop request")
        VECTOR_MANAGER.request_stop()
        if self.path == "/stop_and_wait":
            before = time.perf_counter()
            while time.perf_counter() - before < 30:
                time.sleep(0.1)
                if VECTOR_MANAGER.is_down:
                    break
            else:
                LOGGER.warning("Vector didn't stop after 30 seconds, returning 503")
                self.send_response(503)
                self.end_headers()
                return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        # To disable access logs
        pass


def main():
    LOGGER.info("Starting file-to-loki-log-forwarder")
    LOGGER.info("Generating vector config...")
    generate_vector_config_from_env("conf/vector.yaml.jinja", "conf/vector.yaml")
    LOGGER.info("Validating vector config...")
    res = validate_vector_config("conf/vector.yaml")
    if not res:
        die()
    LOGGER.info("Registering signal handlers...")
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    LOGGER.info("Starting health webserver...")
    health_httpd = ThreadingHTTPServer(
        ("", MANAGEMENT_API_PORT), HealthHTTPRequestHandler
    )
    launch_thread = threading.Thread(target=health_httpd.serve_forever)
    launch_thread.start()
    LOGGER.info("Launching vector...")
    VECTOR_MANAGER.launch_and_wait("conf/vector.yaml")
    LOGGER.info("Stopping health webserver...")
    health_httpd.shutdown()
    launch_thread.join()
    LOGGER.info("File-to-loki-log-forwarder stopped")


if __name__ == "__main__":
    stlog_outputs = _make_default_outputs()
    stlog_outputs.append(ROTATING_FILE_OUTPUT)
    stlog.setup(
        outputs=stlog_outputs, extra_levels={"httpx": "WARNING", "httpcore": "INFO"}
    )
    main()
