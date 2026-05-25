import ollama


class OllamaEmbedder:
    def __init__(self, host: str, model: str):
        self.client = ollama.AsyncClient(host=host)
        self.model = model

    async def embed(self, text: str) -> list[float]:
        vectors = await self.embed_many([text])
        return vectors[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embed(model=self.model, input=texts)
        embeddings = response.get("embeddings")
        if not embeddings:
            raise RuntimeError(f"Ollama returned no embeddings for model {self.model}")
        return [list(vector) for vector in embeddings]
