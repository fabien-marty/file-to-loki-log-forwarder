FROM python:3.12-alpine AS base
FROM base AS builder

##### BUILDER #####

ENV UV_VERSION=0.7.3

# Preparing directories
RUN mkdir -p /app/bin /app/conf

# Install curl, bash, vector and uv
RUN apk add curl bash
COPY install_vector.sh /
RUN /install_vector.sh
RUN pip install "uv==${UV_VERSION}"

# Preparing dependencies
COPY pyproject.toml uv.lock /app/
WORKDIR /app
RUN uv sync --no-dev --frozen

# Copying main files
COPY conf/vector.yaml.jinja /app/conf/
COPY bin/entrypoint.sh bin/main.py /app/bin/

##### BASE #####

FROM base
COPY --from=builder /app /app
RUN mkdir -p /var/lib/vector
ENTRYPOINT ["/app/bin/entrypoint.sh"]
