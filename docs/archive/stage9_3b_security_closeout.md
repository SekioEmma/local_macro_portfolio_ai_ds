# Stage 9.3-B Security Closeout

Status: completed 2026-06-15.

## Scope

This closeout audits the external-AI integration seam from Stage 9.3-A through
Stage 9.3-B-2c. It is not a new feature, does not authorize AI Chat
productization, and does not add endpoint, frontend UI, persistence, search,
agent behavior, or automatic provider calls.

## Verified Chain

The current DeepSeek seam is locked to this chain:

1. AI Context Manifest supplies sanitized context only.
2. The external request builder constructs `ExternalAIRequest` from manifest
   summaries, not raw questions or prompts.
3. `guard_request` blocks missing boundaries, network-mode requests, raw fields,
   private paths, credentials, holdings, account values, position weights,
   transaction history, provider payloads, and search results.
4. `ExternalAIRuntimePolicy` must pass with every approval gate true and every
   dangerous permission false.
5. `build_deepseek_provider_payload` creates a sanitized provider payload with
   restricted message roles and no key, URL, endpoint, model, raw prompt, raw
   response, holdings, account, position, transaction, search, or local path.
6. `DeepSeekTransportRequest` preserves the sanitized transport contract.
7. `DeepSeekRealTransport` is isolated in `deepseek_real_transport.py`.
8. `validate_external_ai_response_content` validates provider text before a real
   external response can return.
9. `guard_external_model_response` is the explicit real-external-response guard.
10. Responses are not saved by default and require human review.

## Route Isolation

No public route exists for `/api/chat`, `/api/search`, `/api/ai/chat`,
`/api/ai/search`, `/api/ai/deepseek`, `/api/ai/external`, `/api/ai/tavily`,
`/api/ai/send`, `/api/ai/complete`, `/api/ai/generate`,
`/api/ai/provider-payload`, or `/api/ai/runtime-policy`.

Stage 9.2 preview endpoints remain local preview surfaces. They do not import
the DeepSeek adapter, real transport, runtime policy, provider builder,
transport request builder, external-response guard, or key loader.

## Secret Handling

The only allowed key-read point is `load_deepseek_api_key_from_env()`.
It reads the process environment variable `DEEPSEEK_API_KEY` only. It does not
load `.env`, read YAML, log keys, return keys through schemas, persist keys, or
place keys in exceptions.

`DeepSeekTransportRequest` and `DeepSeekTransportResponse` do not contain key,
URL, endpoint, model, header, raw provider body, raw prompt, or raw response
fields.

## Privacy Handling

The seam does not send or expose:

- holdings line items
- account values
- position weights
- transaction history
- raw prompts
- raw responses
- raw provider payloads
- local private paths
- search results

Privacy flags must remain manifest-only, no raw prompts, no raw provider
payloads, no search, no persistence, and human review required.

## Output Boundary

The response guards still block action, allocation, forecast, probability, and
guarantee language, including buy/sell, add/reduce/clear position, hedge,
rebalance, target allocation/weight, expected/predicted/future return, market
direction probability, crash probability, recession probability, trade signal,
guaranteed, will rise, and will fall.

Missing context remains missing. AI must not fill missing data.

## Remaining Risks

- The external response validator wrapper is minimal; it is not a full AI
  product validator.
- The internal one-shot invocation workflow is command-line-only and
  manual-only; it is not a product surface.
- No UI or user-confirmation flow is implemented.
- No live DeepSeek call was performed in tests.
- Real provider behavior remains unsurfaced by application endpoints and must
  not be treated as a fact layer.

## Next Step Recommendation

Stage 9.3-B-2d internal one-shot manual invocation review completed.
External AI line frozen. No AI Chat/product endpoint/frontend UI/persistence/
Tavily/search was added. The next step is to return to the core modeling/data
roadmap.

Stage 9.3-B security closeout does not add Chat productization. It does not add
endpoint/UI/persistence/live test. The completed one-shot workflow remains
internal, local-only, command-line-only, and manual-only.

DF-0 roadmap arbitration confirms that the external AI line remains frozen. Any
user-facing AI feature requires separate explicit approval. The next
modeling/data task after DF-0 is D19 v1 historical evidence-row integration.
