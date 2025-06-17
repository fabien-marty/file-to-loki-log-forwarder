# file-to-loki-log-forwarder

[![UV Badge](https://raw.githubusercontent.com/fabien-marty/common/refs/heads/main/badges/uv.svg)](https://docs.astral.sh/uv/)
[![Mergify Badge](https://raw.githubusercontent.com/fabien-marty/common/refs/heads/main/badges/mergify.svg)](https://mergify.com/)
[![Renovate Badge](https://raw.githubusercontent.com/fabien-marty/common/refs/heads/main/badges/renovate.svg)](https://docs.renovatebot.com/)
[![MIT Licensed](https://raw.githubusercontent.com/fabien-marty/common/refs/heads/main/badges/mit.svg)](https://en.wikipedia.org/wiki/MIT_License)

## What is it?

This is a public docker image to forward log lines read from files to loki (based on  [Vector](https://vector.dev/)).

The image integrates a special vector configuration (and some signal handling scripts) to be used in the context of ephemeral containers
(like CloudRun Services/Jobs) as it guarantees that all logs are flushed to loki before the container is killed.

Moreover, it provides a special management and health check endpoint to avoid the container to be killed prematurely or to control the shutdown sequence manually.

> [!WARNING]  
> Probably quite specific to my needs.

## How to use it?

### Quickstart

#### With CloudRun Service

With CloudRun Service, you can use the following image as a sidecar: `docker.io/fabienmarty/file-to-loki-log-forwarder:latest`
with a shared volume mount between the main controller and the sidecar (for example in `/logs`).

Then:
- you have to define a `SOURCE_FILE_INCLUDE_PATHS=/logs/*.log,/logs/*.log.*` env var for example in the sidecar container configuration.
- you also have to define some other env vars (see reference section for more details)
- you must configure your logging in your main container to write to `/logs/foo.log` for example.

With CloudRun Service, the shutdown sequence is gracefully managed by GCP (SIGTERM, and 10s of graceful period before SIGKILL) so you don't need to do anything special.

> [!NOTE]
> If the main container failed to start (but write some logs before exiting), there is a case where the sidecar container is never started (so logs are never seen/forwarded). To avoid this, you can introduce a dependency in the main container to wait for the sidecar container to be started. But it will slow down the startup of the main container. It can be an issue with cold start time for example. Your call!

#### With CloudRun Job

This is the same idea than with CloudRun Service but you have to manage the shutdown sequence manually as GCP doesn't manage it (the sidecar container is brutally killed (`SIGKILL`) just after the main container stops).

So you have to use this entrypoint for your main container:

```sh
#!/bin/sh
# shellcheck disable=SC2317

PID=

signal_handler() {
    echo "Signal received: ${1}"
    if [ "${PID}" != "" ]; then
        kill -0 "${PID}" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "Sending signal to PID: ${PID}"
            kill -s "${1}" "${PID}" 2>/dev/null
        fi
    fi
}

wait_for_log_forwarder_to_be_started() {
    timeout_time=$(( $(date +%s) + 30 ))
    echo "Waiting for the log forwarder to be started..."
    while true; do
        curl --max-time 1 http://localhost:8952/ >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "Log forwarder is started!"
            break
        fi
        sleep 1
        if [ "$(date +%s)" -gt "${timeout_time}" ]; then
            echo "WARNING: The log forwarder didn't start after 30 seconds => let's continue anyway"
            break 
        fi
    done
}

stop_log_forwarded_and_wait() {
    echo "Stopping the log forwarder (and waiting for it to be stopped)..."
    curl -XPOST --max-time 30 http://localhost:8952/stop_and_wait >/dev/null 2>&1
    sleep 1
    curl --max-time 1 http://localhost:8952/ >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "Log forwarder is stopped!"
    else
        echo "Log forwarder is not stopped after 30 seconds => let's continue anyway"
    fi
}

if [ "${LOG_FORWARDER_ENABLED}" = "1" ]; then
    wait_for_log_forwarder_to_be_started
else
    echo "LOG_FORWARDER_ENABLED is not set to 1 => skipping the log forwarder"
fi

trap 'signal_handler TERM' TERM
trap 'signal_handler INT' INT

{YOUR_COMMAND} &
PID=$!

wait "${PID}"
CODE=$?

if [ "${LOG_FORWARDER_ENABLED}" = "1" ]; then
    stop_log_forwarded_and_wait
fi

echo "Exiting with the status code: ${CODE}..."
exit "${CODE}"
```

> [!WARNING]  
> Of course, you have to change the `{YOUR_COMMAND}` to execute your actual command.

> [!TIP]
> Don't mix your code with this entrypoint, put your code in a separate script and call it from this entrypoint.
> (to be sure that all errors are properly catched and to keep a graceful shutdown of the log_forwarder sidecar)

> [!WARNING]
> In production, to activate the log forwarder graceful shutdown, you have to set the `LOG_FORWARDER_ENABLED` environment variable to `1` (in your main container config).

### How to configure `stlog` with Google Cloud Platform (GCP)?

If you use the [stlog](https://github.com/fabien-marty/stlog) library, you can configure like that:

```python
from stlog.setup import _make_default_outputs
from stlog.output import RotatingFileOutput
from stlog.formatter import JsonFormatter, DEFAULT_STLOG_GCP_JSON_FORMAT

stlog_outputs = _make_default_outputs()
if os.environ.get("LOG_FORWARDER_ENABLED", "0") == "1":
    stlog_outputs.append(RotatingFileOutput(
        filename="/logs/stlog.log",
        formatter=JsonFormatter(fmt=DEFAULT_STLOG_GCP_JSON_FORMAT),
        max_bytes=10 * 1024 * 1024,
        backup_count=3,
        delay=True,
    ))
stlog.setup(
    outputs=stlog_outputs
)
```

Don't forget to set `LOG_FORWARDER_ENABLED=1` and `STLOG_OUTPUT=json-gcp` in your main container configuration (only in GCP environment of course).

## Reference

### Mandatory environment variables

- `SOURCE_FILE_INCLUDE_PATHS`: comma separated list of paths to files to read (can include wildcards)
- `SINK_LOKI_ENDPOINT`: the endpoint of the loki instance to send the logs to (note: you can omit it when using `DEBUG=1`)
- `SINK_LOKI_LABELS`: a comma separated list of labels (format: `key=value`) to add to the logs

### Optional environment variables

- `DONT_EXIT`: set this to `1` for Cloud Run Jobs or Cloud Batch (as the shutdown sequence is very special), set this to `0` (default) for Cloud Run Services
- `USE_JSON_FIELD_AS_TIMESTAMP`: if set, we consider that the logs are in JSON format and we use the value of this field as timestamp (must be a valid ISO 8601 timestamp) (only if `CODEC=json`)
- `IGNORE_NON_JSON_LINES`: if set to `1`, we silentyly ignore lines that are not valid JSON (only if `CODEC=json`)
- `SINK_LOKI_TENANT_ID`: the tenant id to use when sending the logs to loki
- `SINK_LOKI_AUTH_STRATEGY`: the authentication strategy to use when sending the logs to loki
- `SINK_LOKI_AUTH_USER`: the username to use when sending the logs to loki
- `SINK_LOKI_AUTH_PASSWORD`: the password to use when sending the logs to loki
- `STLOG_LEVEL`: the log level to use (default: `INFO`) (not for `vector` itself but for the wrapper script used to run it)
- `STLOG_OUTPUT`: `console` (default, for a human formatting of logs) or `json` or `json-gcp` (for structured logging)
- `MANAGEMENT_API_PORT`: management API port to bind to (default: `8952`) (note: don't expose this port to the public internet!, see reference section for more details)
- `INCLUDE_INTERNAL_LOGS`: if set to `1`, we also forward internal logs of this wrapper script to loki
- `INCLUDE_VECTOR_LOGS`: if set to `1`, we also forward internal logs of vector to loki
- `CODEC`: the codec to use when sending the logs to loki (`json` or `text`, default: `json`)
- `DEBUG`: if set to `1`, we enable debug mode (don't use it in production!), it will activate some additional logs, config dump (including passwords!) and a console sink to debug log events

### Management API

The HTTP (not HTTPS!) management API available on the `${MANAGEMENT_API_PORT}` (default to `8952`) offers the following method/endpoints:

- `GET /health`: returns a HTTP/200 if the log forwarder is completely started (note: HTTP/200 is returned even if the log forwarder is stopping to avoid a premature kill of the container)
- `POST /stop`: stops the log forwarder (graceful shutdown)
- `POST /stop_and_wait`: stops the log forwarder (graceful shutdown) and waits for it to be stopped (up to 30 seconds)

## DEV notes

### Prerequisites

- `docker`
- `make`
- `uv` (https://docs.astral.sh/uv/getting-started/installation/)

### Play locally

```
docker run -d --name=loki --network host grafana/loki
docker run -d --name=grafana --network host grafana/grafana
make debug-docker
```

Open a browser on `http://localhost:3000` (`admin/admin` by default), add a loki connection to `http://localhost:3100` and you should be able to see the logs in the loki web interface.

### Architecture

- This is "simple" docker wrapper around vector built with Python ([bin/main.py](bin/main.py)).
- The Vector [configuration file](conf/vector.yaml.jinja) is a Jinja2 template that is rendered at build time with the environment variables.
- Python stuff and dependencies are managed with [uv](https://docs.astral.sh/uv/getting-started/installation/).

### Makefile targets

```
$ make help
clean                          Clean the repository
debug-docker                   Build and run the docker image in pure debug mode
docker                         Build the docker image
install-vector                 Install vector
lint                           Lint the code
no-dirty                       Check that the repository is clean
test                           Run the tests
```
