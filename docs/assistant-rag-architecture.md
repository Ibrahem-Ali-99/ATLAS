# Assistant retrieval and generation

The workspace Assistant answers from one organization's documents and CRM. The retrieval default is `PRODUCTION_PIPELINE = "answerable"` in `apps/api/app/domains/knowledge/retrieval.py`.

Candidate search stays broad. A second stage decides whether a passage actually contains the requested fact. The choice was checked on the Feld development split. The older held-out Feld questions stay a historical benchmark. The fresh Plover Dock set in `app/domains/evaluation/rag_final.py` was scored after the stage was frozen.

## Two stages

1. **Candidates.** The hybrid pool is an AND full-text query, an OR full-text query, and vector neighbors inside the existing cosine cutoff, fused by reciprocal rank `1 / (60 + rank)`. This pool is allowed to include topical neighbors.
2. **Answerability.** `select_answerable` keeps a passage only when the question's rare constraints occur together as positive mentions and the passage has the kind of fact the question asks for: a number, a date, a time, a code, an email, or an address. A negated mention ("is not Feld") does not count. A question joined by "and" plus a following part is searched as separate clauses, and each clause keeps its own current or superseded card. When the question asks for the current fact and both cards are in the pool, the superseded card is dropped. A salary, telephone, mobile, or home-address question is answered only by a passage that states that fact. "No home address is stored" does not answer any of those questions. A clause with no supporting passage is named in the prompt so the model can answer the supported parts and say which part was not found.

The other pipeline names remain callable for comparison: `lexical`, `dense`, `baseline`, `hybrid`, `hybrid_meta`, `hybrid_rerank`, and `hybrid_full`. `search_chunks` still defaults its argument to `hybrid` so older evidence tests keep exercising that path. The Assistant passes `answerable`.

Chunk size stays 800 with overlap 100. The 0.45 and 0.55 distance gates were not moved. A cross-encoder package is not installed, so that comparison was not run. A learned reranker was not added.

## Why dense neighbors are not answers

On local Ollama `nomic-embed-text:v1.5`, development hard negatives landed between cosine distance 0.1973 and 0.3773, inside the 0.45 gate. The Manchester rate question's nearest document was the Feld rate card, because the company name and the words "cold storage" dominate the place name. The home-address question's nearest document was the staff directory, because it names the person. Dense retrieval therefore abstained on none of those questions. The answerability stage abstained on all four.

## Turn order

1. A prompt-injection phrase returns a refusal and does not search.
2. Weather, jokes, and similar unrelated questions return a short boundary.
3. A greeting or a capability question returns the stored reply for that intent.
4. A bare topic asks which company or document the member means.
5. Summary, follow-up, appointment, and task turns read one stored lead and, when needed, store a proposal. A delete or other mutation is refused as read-only.
6. A follow-up pronoun is rewritten from the previous user question. The rewrite does not call a model.
7. Document search uses the answerable pipeline. CRM search still adds leads and contacts of a named company.
8. When nothing qualifies, the reply asks for the company, document, or lead.
9. A grounded model call sees only the passages that survived answerability. The prompt tells the model to copy prices, codes, dates, temperatures, units, and opening hours as written, and to answer every supported part. `attribute_answer` then drops a citation whose text does not contain the number, code, or email in the answer. `80000` and `80,000` are the same figure. `9` and `09` are the same clock component. `19` is not accepted as `9`.

## Public website chat and visitor Assistant sessions

Anonymous website auto-reply and a visitor Assistant session do not call Groq or Ollama unless `ATLAS_PUBLIC_INFERENCE_ENABLED` is true. The default is false, and this work leaves it false.

While the switch is false, a visitor Assistant session keeps the deterministic stand-in. The website widget stores the visitor message and marks the thread for a person.

When the switch is on, both paths call `assess_public_inference` before the model. The Assistant session key is `assistant:{organization_id}:{user_id}`. The widget key is the organization id plus the widget session id. The guard enforces, per API process:

- input length, default 4000 characters
- a minimum gap between messages in one session, default 2 seconds
- a per-session completion budget and a global budget inside a time window
- at most two public generations in flight
- rejection of a prompt-injection phrase, a null byte, a long single-character message, or more than three URLs
- an output-token cap, default 400

The visitor model client uses the deployment's server-side chat settings, not a key stored on the visitor organization. A provider failure is stored as: `Deterministic fallback: the live model did not answer. A person should review this chat. This sentence was not produced by the model.`

Signed-in workspace turns that are not visitor sessions are not counted against the public budget. Visitor embeddings stay on the deterministic embedder.

## Reproduce

```powershell
cd apps/api
uv run pytest tests/test_evidence_answerability.py tests/test_inference_guard.py tests/test_assistant.py -q
$env:ATLAS_LIVE_RAG = "yes"
uv run python -m app.scripts.evaluate_retrieval_experiments
$env:ATLAS_FINAL_EVAL = "yes"
uv run python -m app.scripts.evaluate_final_generation
$env:ATLAS_ACCEPTANCE_EVAL = "yes"
uv run python -m app.scripts.evaluate_acceptance
```

The acceptance command calls Groq through the visitor Assistant. It enables public inference only inside that process. The setting default stays false. Do not set `ATLAS_PUBLIC_INFERENCE_ENABLED` in `.env` for this check.

The measured Orry Beacon results, the remaining misses, and the conversations that stayed factual are in `docs/assistant-rag-evaluation.md`. Retrieval optimization stops at that set. The Assistant is ready for personal product acceptance with those limits recorded.

The live commands send fictional text only. The final command writes Plover rows only inside a transaction on `atlas_test` and rolls them back. Both refuse to run without the environment flags.
