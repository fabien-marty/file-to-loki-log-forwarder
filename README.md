# file-to-loki-log-forwarder

[![UV Badge](https://raw.githubusercontent.com/fabien-marty/common/refs/heads/main/badges/uv.svg)](https://docs.astral.sh/uv/)
[![Mergify Badge](https://raw.githubusercontent.com/fabien-marty/common/refs/heads/main/badges/mergify.svg)](https://mergify.com/)
[![Renovate Badge](https://raw.githubusercontent.com/fabien-marty/common/refs/heads/main/badges/renovate.svg)](https://docs.renovatebot.com/)
[![MIT Licensed](https://raw.githubusercontent.com/fabien-marty/common/refs/heads/main/badges/mit.svg)](https://en.wikipedia.org/wiki/MIT_License)

## What is it?

This is a public docker image to forward log lines read from files to loki (based on  [Vector](https://vector.dev/)).

The image integrates a special vector configuration (and some signal handling scripts) to be used in the context of ephemeral containers
(like CloudRun Jobs) as it guarantees that all logs are flushed to loki before the container is killed.

> [!WARNING]  
> Probably quite specific to my needs.

## How to use it?

### Mandatory environment variables

- `SOURCE_FILE_INCLUDE_PATHS`: comma separated list of paths to files to read (can include wildcards)
- `SINK_LOKI_ENDPOINT`: the endpoint of the loki instance to send the logs to
- `SINK_LOKI_LABELS`: a comma separated list of labels (format: `key=value`) to add to the logs

### Optional environment variables

- `USE_JSON_FIELD_AS_TIMESTAMP`: if set, we consider that the logs are in JSON format and we use the value of this field as timestamp (must be a valid ISO 8601 timestamp)
- `IGNORE_NON_JSON_LINES`: if set to `1`, we silentyly ignore lines that are not valid JSON
- `SINK_LOKI_TENANT_ID`: the tenant id to use when sending the logs to loki
- `SINK_LOKI_AUTH_STRATEGY`: the authentication strategy to use when sending the logs to loki
- `SINK_LOKI_AUTH_USER`: the username to use when sending the logs to loki
- `SINK_LOKI_AUTH_PASSWORD`: the password to use when sending the logs to loki
- `STLOG_LEVEL`: the log level to use (default: `INFO`) (not for `vector` itself but for the wrapper script used to run it)
- `STLOG_OUTPUT`: `console` (default, for a human formatting of logs) or `json` or `json-gcp` (for structured logging)
- `DEBUG`: if set to `1`, we enable debug mode (don't use it in production!)

## Hacking

### Prerequisites

- `docker`
- `make`
- `uv` (https://docs.astral.sh/uv/getting-started/installation/)

### Architecture

This is simple docker wrapper around vector built with Python ([bin/main.py](bin/main.py)).

The Vector [configuration file](conf/vector.yaml.jinja) is a Jinja2 template that is rendered at build time with the environment variables.

Python stuff and dependencies are managed with [uv](https://docs.astral.sh/uv/getting-started/installation/).

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
