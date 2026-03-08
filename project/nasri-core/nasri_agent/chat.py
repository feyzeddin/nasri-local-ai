import os

import httpx


def _ollama_generate(prompt: str) -> str:
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("MODEL_NAME", "llama3")
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(f"{ollama_url}/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
    return str(data.get("response", "")).strip()


def chat_loop() -> int:
    print("Nasri chat basladi. Cikmak icin /exit yaz.")
    while True:
        try:
            user_input = input("Sen: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNasri: Gorusmek uzere.")
            return 0

        if not user_input:
            continue
        if user_input.lower() in {"/exit", "exit", "quit"}:
            print("Nasri: Gorusmek uzere.")
            return 0

        try:
            answer = _ollama_generate(user_input)
            if not answer:
                answer = "Su anda yanit uretemedim."
            print(f"Nasri: {answer}")
        except Exception as exc:
            print(f"Nasri: Ollama baglantisi basarisiz ({exc}).")
