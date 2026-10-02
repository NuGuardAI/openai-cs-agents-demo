"""Shared Azure OpenAI configuration for ChatKit and the legacy API."""
import os
from pathlib import Path

from agents import ModelSettings, set_default_openai_api, set_default_openai_client, set_tracing_disabled
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

AZURE_MODEL = os.environ["AZURE_OPENAI_MODEL_NAME"]
# Chat Completions tools require reasoning to be disabled on the deployed model.
# An empty value leaves reasoning configuration to the SDK for other deployments.
_reasoning_effort = os.getenv("AZURE_OPENAI_REASONING_EFFORT", "none").strip()
AZURE_MODEL_SETTINGS = ModelSettings(
    reasoning={"effort": _reasoning_effort} if _reasoning_effort else None,
)
client = AsyncAzureOpenAI(
    api_key=os.environ["AZURE_OPENAI_KEY"],
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
)
set_default_openai_client(client)
set_default_openai_api("chat_completions")
set_tracing_disabled(True)
