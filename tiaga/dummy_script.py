import httpx
async def test_ollama():
    async with httpx.AsyncClient() as client:
        url = "http://localhost:11434/generate"
        payload = {
            "model": "llama2",
            "prompt": "Hello, Ollama!",
            "stream": True,
        }
        async with client.stream("POST", url, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                print(line.decode())