#!/usr/bin/env python3

import os
import signal
import subprocess
import time
from jinja2 import Template
import stlog

vector_process: subprocess.Popen | None = None
LOGGER = stlog.getLogger("file-to-loki-log-forwarder")


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
    if vector_process is not None:
        LOGGER.info("Waiting 1s...")
        time.sleep(1)
        try:
            vector_process.terminate()  # Send SIGTERM
            LOGGER.info("SIGTERM sent to vector")
        except Exception:
            LOGGER.info("Can't send SIGTERM to vector (already stopped?)")
    else:
        LOGGER.info("No vector process to stop")


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


def launch_vector_and_wait(config: str):
    global vector_process
    vector_process = subprocess.Popen(["bin/vector", "--config-yaml", config])
    while True:
        return_code = vector_process.poll()
        if return_code is not None:
            LOGGER.info("Vector exited with code %s", return_code)
            break
        time.sleep(1)
    vector_process = None


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
    LOGGER.info("Launching vector...")
    launch_vector_and_wait("conf/vector.yaml")
    LOGGER.info("File-to-loki-log-forwarder stopped")


if __name__ == "__main__":
    stlog.setup()
    main()
