# Kong vLLM test

Requires `uv` and and API key from https://portal.test.drai.auckland.ac.nz

```
uv sync
export OPENAI_API_KEY=my-api-key
uv run python main.py
```

To test the embedding model (after running about commands):

```
uv run python test-embedding.py
```

To test LiteLLM (make sure `OPENAI_API_KEY` is set):

```
uv run python test-litellm.py
uv run python test-litellm-embedding.py
```
