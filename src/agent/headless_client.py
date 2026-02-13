from openai import OpenAI
import time

# Point to our broker
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="range-crawler-secret" # Not used by broker currently, but required by client
)

def test_listing_models():
    print("Listing models...")
    models = client.models.list()
    for model in models:
        print(f"- {model.id}")

def test_completion(model_name="facebook/opt-125m"):
    print(f"
Generating text with model: {model_name}")
    start = time.time()
    try:
        completion = client.completions.create(
            model=model_name,
            prompt="The capital of France is",
            max_tokens=10
        )
        duration = time.time() - start
        print(f"Response (took {duration:.2f}s): {completion.choices[0].text}")
    except Exception as e:
        print(f"Error: {e}")

def test_chat_completion(model_name="facebook/opt-125m"):
    print(f"
Chatting with model: {model_name}")
    start = time.time()
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2+2?"}
            ]
        )
        duration = time.time() - start
        print(f"Response (took {duration:.2f}s): {completion.choices[0].message.content}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Note: The first request for a model will trigger loading, which takes time.
    test_listing_models()
    test_completion()
    test_chat_completion()
    test_listing_models() # Should show the loaded model now
