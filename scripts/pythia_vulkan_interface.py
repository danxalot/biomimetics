import json
import requests


def query_pythia_vulkan(prompt, max_tokens=512, temperature=0.2, stop=None):
    """
    Communicate with the Pythia model via the Vulkan-accelerated llama.cpp server on port 11435.

    This function sends a prompt to the existing llama.cpp server running on
    http://localhost:11435/v1 (which uses Vulkan device 0 for acceleration) and
    returns the generated completion.

    Args:
        prompt (str): The input prompt to send to the model
        max_tokens (int): Maximum number of tokens to generate (default: 512)
        temperature (float): Sampling temperature (default: 0.2)
        stop (list or str): Stop sequences for generation (default: None)

    Returns:
        str: The generated text completion

    Example:
        >>> response = query_pythia_vulkan("Explain quantum computing in simple terms")
        >>> print(response)
        "Quantum computing is a type of computing that uses quantum-mechanical phenomena..."
    """
    url = "http://localhost:11435/v1/completions"

    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    if stop is not None:
        payload["stop"] = stop

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            return result["choices"][0]["text"].strip()
        else:
            return f"Error: Unexpected response format: {result}"

    except requests.exceptions.RequestException as e:
        return f"Error communicating with Pythia server: {str(e)}"
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return f"Error parsing response from Pythia server: {str(e)}"


def query_pythia_vulkan_and_log(prompt, max_tokens=512, temperature=0.2):
    """Executes the Pythia query and automatically logs the result to CoPaw Memory."""
    import datetime

    response = query_pythia_vulkan(prompt, max_tokens, temperature)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"pythia-contact-{timestamp}"
    content = f"# Pythia Dragonfly First Contact\n\n**Timestamp:** {timestamp}\n**Prompt:** {prompt}\n\n**Response:**\n{response}"

    try:
        requests.put(
            f"http://127.0.0.1:8088/api/agent/memory/{fname}",
            data=content,
            headers={"Content-Type": "text/plain"},
            timeout=5,
        )
        print(f"✅ Pythia interaction logged to Infinimemory: {fname}")
    except Exception as e:
        print(f"⚠️ Failed to log Pythia interaction: {e}")

    return response


# Example usage:
if __name__ == "__main__":
    # Test the function
    test_prompt = "The future of artificial intelligence is"
    result = query_pythia_vulkan(test_prompt, max_tokens=100)
    print(f"Prompt: {test_prompt}")
    print(f"Response: {result}")
