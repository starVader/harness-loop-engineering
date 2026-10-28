# The sandbox for actor-written code: Python and pytest, nothing else.
# Build once with `python -m harness.sandbox build`; harness/sandbox.py runs it
# with no network, read-only mounts and resource limits.
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest==9.1.1
RUN useradd --uid 1000 --create-home runner
USER 1000
WORKDIR /w
