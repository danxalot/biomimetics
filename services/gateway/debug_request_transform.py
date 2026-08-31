
import os
import sys

# Mocking the environment
os.environ["OLLAMA_API_KEY"] = "mock_ollama_key"
os.environ["OLLAMA_HOST"] = "http://host.docker.internal:11435"

# Mocking model_config
model_config_mock = {
    "minimax-2.1": {"provider": "minimax"},
    "glm-4v-flash": {"provider": "bigmodel"}
}

def transform_request(model_name):
    print(f"--- Transforming Request for {model_name} ---")
    
    # Logic from main.py
    config = model_config_mock.get(model_name)
    if not config:
        print(f"Model {model_name} not found in config")
        return

    provider = config.get("provider")
    actual_model = model_name
    
    params = {
        "model": actual_model,
        "messages": [{"role": "user", "content": "test"}],
    }

    if provider == "minimax" or provider == "bigmodel" or provider == "zhipu":
         params["model"] = f"openai/{actual_model}"
         
         ollama_host = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11435")
         if not ollama_host.startswith("http"): ollama_host = f"http://{ollama_host}"
         if ":11435" not in ollama_host: ollama_host = f"{ollama_host}:11435"
         if not ollama_host.endswith("/v1"): ollama_host = f"{ollama_host}/v1"
            
         params["api_base"] = ollama_host
         api_key = os.getenv("OLLAMA_API_KEY")
         params["api_key"] = api_key
         
         if api_key:
             params["extra_headers"] = {"Authorization": f"Bearer {api_key}"}

    print(f"Final Params passed to litellm.acompletion:")
    print(f"  model: {params.get('model')}")
    print(f"  api_base: {params.get('api_base')}")
    print(f"  api_key: {params.get('api_key')}")
    print(f"  extra_headers: {params.get('extra_headers')}")
    print("------------------------------------------------")

if __name__ == "__main__":
    transform_request("minimax-2.1")
    transform_request("glm-4v-flash")
