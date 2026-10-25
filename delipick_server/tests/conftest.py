"""Tests are offline/replay even when invoked in a live API container."""
import os

# Apply before deployment.app or recommend_logic can be imported by collection.
os.environ["ENABLE_DELIVERY_WORKER"] = "false"
os.environ["QUERY_MODE"] = "replay"
os.environ["OPENAI_API_KEY"] = ""
