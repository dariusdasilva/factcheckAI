"""Development settings — safe defaults for local runs and hermetic tests."""

from .base import *  # noqa: F403

DEBUG = True

# QAT model / Ollama endpoints arrive with Chunk B; nothing to wire here yet.
