# Assistant retrieval evaluation

Recorded on 26 November 2026. The decision set is fictional Feld and Quay logistics text in `app/domains/evaluation/rag_dataset.py`. It is not the Harbor demo workspace and it was not written into the development database. Retrieval ran on the disposable `atlas_test` database and was discarded by the test fixture.

The earlier eight-question Marrow comparison remains in `tests/test_rag_pipeline.py`. That set has no hard negative that shares topic words with a real document, so hybrid looked uniformly better there. It is not the selection set.

## Dataset

116 labeled questions. 39 are development (`dev-001` onward). 77 are held out (`held-001` onward). The lists are written in the file. They are not shuffled after a score.

Development covers paraphrases, one keyword code, multi-document questions, hard negatives, a current rate beside a superseded rate and a competitor rate, numbers, dates, four conversational follow-ups, one CRM lead question, one unsupported home-address question, and one prompt injection.

Held-out continues those kinds and adds bare ambiguous nouns, unrelated questions, more injections, and business-action requests. Six held-out questions were marked `live_sample` before any score was read. Lexical search returned no passage for those six, so they were not sent to Groq as an end-to-end generation sample. The Groq calls below use the document text directly and are labeled as such.

## Selection rule

`choose_pipeline` was fixed before the held-out run. It drops any pipeline whose development abstention accuracy is more than 0.05 below the best. Among the rest it picks the highest Recall@5. A tie keeps the earlier name in this order: lexical, dense, baseline, hybrid, hybrid_meta, hybrid_rerank, hybrid_full. Held-out numbers are reported and do not change `PRODUCTION_PIPELINE`.

## Metric definitions

Ranked metrics use K = 5. A relevant id is the document filename stem.

- Recall@5 is the overlap of retrieved titles with the labeled titles, divided by the number of labeled titles. It is averaged over questions whose task is `retrieve`. Follow-ups are excluded from this column.
- nDCG@5 uses binary gains on the same questions.
- Abstention accuracy is the fraction of `abstain` questions that return no row. A hard negative and an unsupported question are abstentions. An unrelated question is an intent label, not an abstention.
- Development follow-up recall is scored separately, raw question against the rewritten question, on the lexical path.
- Deterministic generation, on held-out `retrieve` and `follow_up` questions, does not call a model. Factual correctness is 1 when every labeled term is in the retrieved text, no forbidden term is in that text, and a relevant title was retrieved. Completeness is the fraction of labeled terms present. Faithfulness is 1 when `attribute_answer` does not replace the built answer with "I could not confirm". Citation correctness is 1 when every cited title is in the relevant set. Latency is the mean of the search that feeds that score, in milliseconds, on this machine.
- Intent accuracy is the rule router against the labeled intent. It does not call a model.
- Groq results are a separate section. They are not mixed into the deterministic scores.

Hash embeddings are the reproducible index. They are not a semantic model.

## Development results

Hash embeddings, chunk size 800. The printed run is `DEV_PIPELINE` from `tests/test_rag_qualification.py`.

| Pipeline | Recall@5 | Abstention | nDCG@5 | Latency |
|---|---:|---:|---:|---:|
| lexical | 0.3571 | 0.7500 | 0.3571 | 8.91 ms |
| dense | 0.1786 | 0.7500 | 0.1786 | 9.13 ms |
| baseline | 0.4821 | 0.2500 | 0.4730 | 9.24 ms |
| hybrid | 0.8929 | 0.0000 | 0.8900 | 13.88 ms |
| hybrid_meta | 0.8393 | 0.0000 | 0.8404 | 12.80 ms |
| hybrid_rerank | 0.8929 | 0.0000 | 0.9056 | 17.37 ms |
| hybrid_full | 0.8393 | 0.0000 | 0.8561 | 17.07 ms |

The rule selected lexical. Hybrid recall is higher, and its abstention is 0, so it is dropped. Reranking raised hybrid nDCG from 0.8900 to 0.9056 and did not restore abstention. The title filter lowered recall. Neither was adopted.

Chunk sizes 400, 800, and 1600 each scored a 0.4643 term-in-blob rate on the baseline path. Chunk size stayed 800.

Lexical follow-up recall was 0.75 raw and 0.75 rewritten. Rewrite is not a measured gain on these four questions.

The CRM question "What leads does Feld and Quay have?" was found by word search and by the company link, and the Pantry Club tea lead stayed out. The link is not justified by that question, because the lead title already contains "Quay". It stays because the older Marrow case still fails word search when the lead title omits the company name and succeeds with the company link.

## Held-out results

Same index and the same seven pipelines. Rewrite was off for every pipeline so the retrievers are compared on the question text. `HELD_COMPARE` from the same test:

| Pipeline | Recall@5 | Abstention | nDCG@5 |
|---|---:|---:|---:|
| lexical | 0.1702 | 1.0000 | 0.1702 |
| dense | 0.0745 | 1.0000 | 0.0769 |
| baseline | 0.3511 | 0.7500 | 0.3469 |
| hybrid | 0.8298 | 0.1250 | 0.7623 |
| hybrid_meta | 0.8085 | 0.1250 | 0.7599 |
| hybrid_rerank | 0.8298 | 0.1250 | 0.7696 |
| hybrid_full | 0.8085 | 0.1250 | 0.7672 |

Lexical held-out retrieval latency was 11.75 ms. The production constant stayed lexical after this table was printed.

Deterministic generation on the 47 held-out retrieve and follow-up questions, using lexical retrieval:

| Measure | Score |
|---|---:|
| Factual correctness | 0.1277 |
| Completeness | 0.1277 |
| Faithfulness | 0.1277 |
| Citation correctness | 0.0851 |
| Mean latency | 10.79 ms |

These generation numbers are low because lexical retrieval missed most paraphrases. They are not Groq scores. Intent accuracy on the labeled intent questions was 1.0.

## Failure examples

Lexical development misses, from `DEV_MISS`. Each paraphrase returned no row:

- "How much does Feld charge each week to keep one pallet cold?"
- "Where is the bonded facility in Bristol?"
- "How quickly must a customer file after damaged cargo arrives?"
- "When does the yard shut for Christmas 2026?"
- "What temperature are the frozen rooms kept at?"
- "What has to be paid before the first pallet is accepted?"
- "Is Saturday morning receiving open?"
- The multi-document, conflict, numeric, and date questions in the development list also returned no row. The keyword question that names `FELD-COLD-18` is the kind lexical still hits.

One development abstention failed. "What is Nora Feld's home address?" retrieved `feld-directory` because that file names Nora Feld and does not contain a home address. Abstention on the other three hard negatives held, which is the 0.75 score.

Hybrid abstention is 0 on development because the OR query accepts a chunk that shares two topic words. A question about a Manchester rate or a pantry still overlaps "Feld", "cold", or "yard" with a real document. That is the reason the higher recall was not adopted. The 0.45 and 0.55 cutoffs were not loosened to chase the miss list.

## Semantic probe and Groq

These calls are not part of the deterministic table. `verify_feld_generation.py` was run with `ATLAS_LIVE_RAG=yes`. It embedded fictional Feld text with local Ollama and called Groq. It did not read the demo organization and did not insert rows. The process log recorded `trace_record_failed` because there is no request trace to attach. That is not a model failure.

Ollama `nomic-embed-text:v1.5` embedded the development paraphrases, the development hard negatives, and the whole documents. This is a document-level probe, not a reindex of chunks. The existing 0.45 gate was applied and was not changed.

- Paraphrase hits: 8 of 8.
- Abstentions: 0 of 4. Every hard negative had a neighbor inside 0.45.
- Nearest distances: a Northglass question to `northglass-rate` at 0.2907, a Feld-versus-competitor question to `feld-rate-2026` at 0.1973, a yard hard negative to `feld-bonded-yard` at 0.2782, and the home-address question to `feld-directory` at 0.3773.

Real embeddings retrieve the paraphrases that lexical misses. At the current gate they also retrieve a document for every development hard negative. That probe did not become the production path.

Groq `openai/gpt-oss-20b` saw the document text in the prompt, which is a generation check, not a retrieval success.

- Keyword question at `max_tokens` 120: 624 ms, 120 completion tokens, empty content. The reasoning tokens consumed the cap, so there was no answer to score.
- Same question at the public cap of 400 tokens: 794 ms, 297 prompt tokens, 353 completion tokens. The answer identified `FELD-COLD-18` as the current cold-storage rate of 18 pounds per pallet per week, effective 1 March 2026. It did not mention the superseded 14 pound rate and it contained no key material.
- Unsupported home-address question with the directory excerpt: one run answered "The home address of Nora Feld was not found." (56 completion tokens). A later run answered "No home address is stored." (43 completion tokens, 412 ms). Neither invented an address or a key.

An earlier six-sentence Ollama and Groq check on Marrow text is still available from `verify_rag_live.py`. It is a distance check on the 0.45 gate, not this qualification.

## Business actions

The rule router still scores follow-up, appointment, task, summary, mutation, capability, and greeting without a model. `tests/test_assistant_operations.py` checks the stored path: a summary stays in the tenant, a delete creates no task, confirming a task creates one task and a second confirm returns 409, and a follow-up draft creates a pending approval with no email row. No live email or calendar call was made.

## Public inference

`ATLAS_PUBLIC_INFERENCE_ENABLED` remains false. The budgets, input cap, output cap, concurrency cap, injection rejection, abuse checks, tenant session key, and labeled deterministic fallback are implemented and covered by `tests/test_inference_guard.py`. This run did not enable the switch and did not send an anonymous widget session to Groq.

## Limits

- Hash embeddings decide the default. The Ollama probe shows that a real embedder retrieves paraphrases and also fails the hard negatives at the current gate. A later development run on a real index could change the choice. This held-out table must not be the place that change is made.
- Lexical recall of 0.17 on held-out questions is the cost of the abstention rule. Most paraphrases never reach the model.
- Deterministic generation scores the retrieved text. They will move only when retrieval moves.
- The Groq sample is two questions with the source passage supplied. It is not a claim that the lexical path retrieved those passages.
- English full-text stemming only. Budgets are per API process. There is no cross-encoder.
