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

sleep 60 &
PID=$!

wait "${PID}"
CODE=$?

if [ "${LOG_FORWARDER_ENABLED}" = "1" ]; then
    stop_log_forwarded_and_wait
fi

exit "${CODE}"
