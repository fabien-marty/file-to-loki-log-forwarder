UV=uv
UV_RUN=$(UV) run
FIX=1
IMAGE=docker.io/library/file-to-loki-log-forwarder:latest
HEALTH_PORT=8952

bin/vector:
	./install_vector.sh

.PHONY: install-vector
install-vector: bin/vector ## Install vector

.PHONY: lint
lint: ## Lint the code
ifeq ($(FIX), 1)
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .
else
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
endif
	$(UV_RUN) mypy --check-untyped-defs .

.PHONY: test
test: bin/vector ## Run the tests
	$(UV_RUN) pytest .

.PHONY: clean
clean: ## Clean the repository
	rm -Rf .venv .*_cache build dist htmlcov 
	find . -type d -name __pycache__ -exec rm -Rf {} \; 2>/dev/null || true
	rm -Rf bin/vector vector_installer tmp_vector

.PHONY: docker
docker: ## Build the docker image
	docker build --progress plain -t $(IMAGE) .

.PHONY: debug-docker
debug-docker: ## Build and run the docker image in pure debug mode
	rm -Rf debug_logs
	mkdir debug_logs
	$(MAKE) docker
	docker run -p $(HEALTH_PORT):$(HEALTH_PORT) -v $(pwd)/debug_logs:/logs --rm -it -e STLOG_LEVEL=DEBUG -e IGNORE_NON_JSON_LINES=0 -e DEBUG=1 -e SINK_LOKI_LABELS=job=test,instance=test -e SOURCE_FILE_INCLUDE_PATHS=/logs/*.log $(IMAGE)
	rm -Rf debug_logs

.PHONY: no-dirty
no-dirty: ## Check that the repository is clean
	if test -n "$$(git status --porcelain)"; then \
		echo "***** git status *****"; \
		git status; \
		echo "***** git diff *****"; \
		git diff; \
		echo "ERROR: the repository is dirty"; \
		exit 1; \
	fi

.PHONY: help
help:
	@# See https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
