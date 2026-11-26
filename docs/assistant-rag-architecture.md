# Assistant retrieval and generation

The workspace Assistant answers from one organization's documents and CRM. The retrieval default is `PRODUCTION_PIPELINE = "lexical"` in `apps/api/app/domains/knowledge/retrieval.py`. That choice comes from the development half of the Feld and Quay set in `docs/assistant-rag-evaluation.md`. The held-out half was not used to change it.

## Selected path

Lexical search is an English `plainto_tsquery` that requires every content word. A chunk is evidence only when that query matches. There is no vector neighbor and no OR query on this path.

The other paths remain callable for the benchmark:

| Name | What it searches |
|---|---|
| `lexical` | AND full-text only. This is the Assistant default. |
| `dense` | Vector neighbors only, citable at cosine distance 0.45 or closer. |
| `baseline` | Vector neighbors inside the 0.55 cutoff, AND full-text, reciprocal-rank fusion `1 / (60 + rank)`, evidence when the chunk is lexical, shares a content word, or is at distance 0.45 or closer. |
| `hybrid` | Baseline plus an OR `to_tsquery`. A partial-only hit needs two shared content words, or half of them. |
| `hybrid_meta` | Hybrid, then a title filter when exactly one title shares a distinctive question word. |
| `hybrid_rerank` | Hybrid, reordered by overlap, similarity, title overlap, and an AND-match bonus. Not a cross-encoder. |
| `hybrid_full` | Rerank, title filter, and same-document dedup at Jaccard 0.85. |

`search_chunks` still defaults its argument to `hybrid` so older evidence tests keep exercising that experiment. The Assistant passes `PRODUCTION_PIPELINE` explicitly.

## What stayed

- Organization scope, the ready-document filter, and the pgvector column for the active embedding width.
- The vector-only gate of cosine distance 0.45 and the candidate cutoff of 0.55. Neither cutoff was moved after the qualification run.
- Chunk size 800 and overlap 100. Development scoring at 400, 800, and 1600 was a tie, so the constants did not change.
- Grounded prompts that treat excerpts and CRM rows as untrusted data.
- Citation selection in `attribute_answer`. A number, code, or email in the answer must appear in a retrieved passage, or the stored answer says the fact could not be confirmed.
- Follow-up drafts and appointment requests still become approvals. A task is created only after the member confirms it. Nothing is sent or booked from the chat turn itself.

## Turn order

1. A prompt-injection phrase returns a refusal and does not search. The refusal does not repeat the payload.
2. Weather, jokes, recipes, sports scores, and similar unrelated questions return a short boundary. They are not retrieval abstentions.
3. A greeting or a capability question returns the stored reply for that intent. Capability replies name CRM, knowledge, approvals, and the rule that a person approves and then executes a send.
4. A bare topic such as "rates" or "yard" asks which company or document the member means.
5. Summary, follow-up, appointment, and task turns read one stored lead and, when needed, store a proposal. A delete or other mutation is refused as read-only.
6. A follow-up pronoun is rewritten from the previous user question and cited titles. The rewrite does not call a model. On the development follow-ups it did not raise lexical recall, and it did not lower it. The Assistant still applies it.
7. Document search uses the lexical path. CRM search still adds leads and contacts of a named company, because a lead title does not always repeat the company name.
8. When nothing qualifies, the reply asks for the company, document, or lead. It does not invent a fact.
9. A grounded model call sees only the retrieved rows. `attribute_answer` then drops citations the answer does not use.

## Public website chat

Anonymous website auto-reply does not call Groq or Ollama unless `ATLAS_PUBLIC_INFERENCE_ENABLED` is true. The default is false, and this work leaves it false. While it is false, the widget stores the visitor message and marks the thread for a person. It does not add an outbound model message.

When the switch is on, `assess_public_inference` runs before the model call. The session key is the organization id plus the widget session id, so one tenant cannot spend another's budget. The guard enforces, per API process:

- input length, default 4000 characters
- a minimum gap between messages in one session, default 2 seconds
- a per-session completion budget and a global budget inside a time window
- at most two public generations in flight
- rejection of a prompt-injection phrase, a null byte, a long single-character message, or more than three URLs
- an output-token cap, default 400

A provider failure stores the handoff reason `Deterministic fallback: the live model did not answer. A person should review this chat. This sentence was not produced by the model.` The widget does not invent a visitor-facing answer in that case. Visitor demo organizations still receive the deterministic stand-in from `get_chat_client` before this path. Signed-in workspace turns are not counted against the public budget. The counters live in the API process.

## Reproduce

```powershell
cd apps/api
uv run pytest tests/test_rag_qualification.py tests/test_rag_pipeline.py tests/test_inference_guard.py tests/test_assistant_routing.py -q
$env:ATLAS_LIVE_RAG = "yes"
uv run python -m app.scripts.verify_rag_live
uv run python -m app.scripts.verify_feld_generation
```

The live scripts send fictional sentences only, write no database rows, and refuse to run without `ATLAS_LIVE_RAG=yes`. The qualification corpus is `app/domains/evaluation/rag_dataset.py`. The smaller Marrow corpus in `rag_corpus_v1.json` is the earlier experiment, not the selection set.
