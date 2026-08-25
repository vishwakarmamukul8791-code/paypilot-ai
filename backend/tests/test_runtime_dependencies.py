from __future__ import annotations


def test_langgraph_runtime_initializes_with_installed_dependencies(tmp_path):
    from app.agents.runtime import LangGraphRuntime

    runtime = LangGraphRuntime(str(tmp_path / "langgraph-runtime.db"))
    try:
        assert runtime.mode == "langgraph"
    finally:
        runtime.close()


def test_google_genai_sdk_exposes_interactions_client():
    from google import genai

    client = genai.Client(api_key="test-key")
    try:
        assert hasattr(client, "interactions")
    finally:
        client.close()
