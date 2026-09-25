# Model boundary

Future model adapters implement `ModelProvider`. Keeping the interface here allows local, hosted, or test providers to be swapped without changing orchestration.

## Contract

The agent sends a `ModelRequest` to `ModelProvider.generate()` and receives a
`ModelResponse`. Responses can contain text, structured data, tool-call
requests, finish information, and `ModelMetadata`. Providers report failures
with `ModelError`; timeouts use `ModelTimeoutError`.

## Adding a provider

1. Implement `ModelProvider.generate(request)` in a new adapter module.
2. Translate the provider's native response into `ModelResponse`, including
	`ToolCallRequest` values and provider/model metadata.
3. Translate provider failures and deadline failures into `ModelError` or
	`ModelTimeoutError`.
4. Register construction in `ModelProviderFactory`.

The adapter may depend on a vendor SDK. `AgentController`, tools, security,
memory, and RAG must depend only on the contracts in `provider.py`. The current
factory supports `mock` for tests; no real Ollama connection is implemented.
