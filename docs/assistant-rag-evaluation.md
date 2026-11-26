# Assistant retrieval evaluation

Recorded on 26 November 2026. Three sets are kept apart.

- **Feld development** (`dev-001` onward in `rag_dataset.py`) is the only split used to shape answerability.
- **Feld held-out** (`held-001` onward) was already inspected. It remains the historical benchmark in the previous revision of this note. It was not used to change the pipeline.
- **Plover Dock final** (`final-001` onward in `rag_final.py`) was written before it was scored and was not edited after the scores below.
- **Orry Beacon acceptance** (`rag_acceptance.py`) was written after the Plover scores and was not edited after its own score. It is the last measured set. Retrieval rules were not changed to chase it.

The engineering targets were 85% Recall@5, 90% abstention accuracy, and 85% factual correctness on the fresh set. Recall cleared the target. Abstention and factual correctness did not. The questions and the answerability rules were not changed after those scores were read.

## Metric definitions

Ranked metrics use K = 5. A relevant id is the document filename stem.

- Recall@5, MRR, and nDCG@5 cover questions whose task is `retrieve` or `follow_up`. Follow-ups are rewritten from the previous user question before search. nDCG uses binary gains.
- Abstention accuracy is the fraction of `abstain` questions that return no row.
- Factual correctness, on the Plover set, is the fraction of retrieve and follow-up questions whose Groq answer contains every labeled term and none of the forbidden terms. A question with no retrieved passage scores 0 and is not sent to Groq. Unicode spaces and hyphens are normalized. That published Plover figure does not treat `80000` and `80,000` as the same number.
- The acceptance scorer in `fact_match.py` is separate. `80000`, `80,000`, and `80 000` match. `09:15` and `9:15` match. `18 pounds` and `18 pound` match. `18` does not match `19`, `8 drums` does not match `18 drums`, and a missing code does not match a price that merely contains the same digits. The Plover factual figure was not recomputed with this scorer.
- Completeness is the fraction of labeled terms present in that answer.
- Faithfulness and citation correctness are scored only on the calls that were made. Faithfulness is 1 when `attribute_answer` does not replace the answer with "I could not confirm" and no forbidden term appears. Citation correctness is 1 when every cited title is in the relevant set and at least one citation remains.
- Retrieval latency is the mean of `search_chunks` on this machine. Generation latency is the mean Groq call, not including the two-second pause used to stay under the provider rate limit.
- Token counts are the provider usage fields for those calls.

Hash embeddings are the index inside `search_chunks` for the database runs. Ollama `nomic-embed-text:v1.5` is a separate development experiment and is not the index the Assistant uses in the test database.

## Development results

Full Feld documents as the candidate pool, answerability only: Recall@5 1.0, MRR 1.0, nDCG@5 1.0, abstention 1.0, on 32 retrieve and follow-up questions and 4 abstentions.

The same questions through `search_chunks(..., pipeline="answerable")` with hash embeddings and PostgreSQL full text, one chunk per document: Recall@5 1.0, MRR 0.9792, nDCG@5 0.9844, abstention 1.0.

Ollama document embeddings, development retrieve and abstain questions only:

| Path | Recall@5 | MRR | nDCG@5 | Abstention |
|---|---:|---:|---:|---:|
| Token-overlap lexical | 1.0000 | 0.9375 | 0.9533 | 0.0000 |
| Dense, distance ≤ 0.45 | 0.9286 | 0.8452 | 0.8665 | 0.0000 |
| Hybrid candidates | 1.0000 | 0.9821 | 0.9868 | 0.0000 |
| Hybrid candidates plus answerability | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Nearest dense neighbor for each development abstention:

| Question | Nearest document | Distance |
|---|---|---:|
| What does the staff pantry charge for cold storage? | northglass-rate | 0.2907 |
| What is Feld and Quay's Manchester cold storage rate? | feld-rate-2026 | 0.1973 |
| How many spare chairs are stored in the bonded yard? | feld-bonded-yard | 0.2782 |
| What is Nora Feld's home address? | feld-directory | 0.3773 |

All four are inside the 0.45 gate. The Manchester question is closer to the Feld rate card than to a rival rate because the embedding tracks the company and the topic, not the missing city. The directory is close to a home-address question because it names Nora Feld and then says that no home address is stored. Hybrid candidate search abstains on none of them. Answerability abstains on all four, which is why that stage is the default and dense retrieval is not.

`sentence_transformers` is not installed. A cross-encoder was not compared. The second stage is the deterministic answerability check, not a model call.

## Fresh Plover Dock results

45 questions: 35 retrieve or follow-up, 10 abstentions. Indexed with the production chunker (800 characters, overlap 100), hash embeddings, and `search_chunks` on `atlas_test`. The rows were rolled back.

| Measure | Result | Target |
|---|---:|---:|
| Recall@5 | 0.9286 | 0.85 |
| MRR | 0.9286 |  |
| nDCG@5 | 0.9213 |  |
| Abstention accuracy | 0.8000 | 0.90 |
| Mean retrieval latency | 10.81 ms |  |

Groq `openai/gpt-oss-20b`, 33 calls, `max_tokens` 800. Two retrieve questions had no passage, so they were not sent. Prompt tokens 9477. Completion tokens 5173. Mean generation latency 574 ms.

| Measure | Result | Target |
|---|---:|---:|
| Factual correctness | 0.7143 | 0.85 |
| Completeness | 0.8000 |  |
| Faithfulness | 0.7273 |  |
| Citation correctness | 0.7273 |  |

Factual correctness counts the two retrieval misses as wrong. Faithfulness and citation are the mean over the 33 calls.

## Failure examples

Retrieval misses on the fresh set:

- "What temperature is the freezer store kept at?" returned no passage.
- "When did the old Plover fee end?" returned no passage.
- "What is the account bond and when are dock invoices due?" returned the bond document and not the invoice document.

Abstention misses:

- "What is Ivo Plover's mobile number?" returned the directory, the shed, and the crane procedure.
- "What salary does the dock office lead earn?" returned the directory.

Generation misses where retrieval had already found the right document:

- The current quay fee was stated as 27 pounds per tonne per day and the code `PLOVER-QUAY-27` was left out.
- The Hull shed answer gave 9 Dock Street and left out "15 containers".
- Sunday gate access was answered "yes" without the labeled time `09:00`.
- The superseded card was identified as `PLOVER-QUAY-19` without the words "19 pounds".
- The Bramble rate was stated as 31 pounds without `BRAMBLE-ROAD-31`.
- Hull insurance was stated as 80,000 pounds. The label is the digits `80000`, so the string check failed.

Those generation misses are omitted details or a thousands separator, not a contradicted rate. The published factual score still uses the strict string rule.

## What was kept

Hybrid search remains the candidate generator because, with Ollama embeddings, it reached Recall@5 of 1.0 on the development questions. It is not the final filter: its abstention on that split was 0.

Answerability is the default because it kept that recall and raised development abstention from 0 to 1.0, including on the hash-embedding database index. Title filtering, the earlier second-stage rank, and a cross-encoder were not adopted. Chunk size was not changed.

The superseded-card rule is part of answerability. On the Feld development questions it kept the current 18 pound card and still returned the 2024 card when the question asked which card is superseded.

## Public inference

`ATLAS_PUBLIC_INFERENCE_ENABLED` remains false. The budgets, caps, concurrency limit, injection rejection, and labeled fallback apply to a visitor Assistant session as well as the website widget once the switch is turned on. This run did not turn it on. Visitor embeddings remain deterministic. No service was purchased.

## Limits

- The fresh-set abstention score is 0.80, under the 0.90 target. Two unsupported questions about the dock lead still retrieved the directory.
- Factual correctness is 0.71 under a strict term match. It is under the 0.85 target.
- The Ollama comparison embeds whole documents. The database score uses chunks and hash embeddings.
- The Groq sample is 33 fictional calls. It is not a claim about a visitor session, because public inference is off.
- English full-text stemming only. Budgets are per API process. There is no cross-encoder.

## Orry Beacon acceptance

Scored once on 26 November 2026 after the answer-quality changes. 26 questions: 18 retrieve or follow-up, 8 abstentions. Same chunker, hash embeddings, and `search_chunks(..., pipeline="answerable")` on `atlas_test`. Development recall stayed 1.0 on the Feld questions. The Orry questions were not edited after this score, and the retrieval rules were not changed to raise it.

| Measure | Result |
|---|---:|
| Recall@5 | 0.8056 |
| MRR | 0.8333 |
| nDCG@5 | 0.8118 |
| Abstention accuracy | 1.0000 |
| Mean retrieval latency | 11.62 ms |
| Factual correctness | 0.5000 |
| Completeness | 0.5648 |
| Citation correctness | 0.7222 |
| Partial-answer check | 1.0000 |
| Formatting-only term misses | 0 |

Generation used the visitor Assistant path. With the switch left at its default, `get_chat_client(..., public_inference=True)` returned `DeterministicChatClient`. The acceptance process then enabled the switch only in memory. The client became `OpenAICompatibleChatClient`, capped at 400 output tokens, and each call went through `assess_public_inference`. Groq `openai/gpt-oss-20b` answered under that cap. The loaded setting and the field default were both false after the run. A separate in-process check allowed 8 assessments on one session key and denied the next with `public_inference_session_budget`.

Abstention covered salary, mobile number, home address, store telephone, and four hard negatives. None of those eight questions returned a passage, so none were sent to the model.

Retrieval misses:

- "When did the old lamp oil fee end?" returned no passage.
- "When does the current fee start, and when did the old fee end?" returned only the current card. The model stated 12 July 2026 and said the old end date was not found.
- "What temperature is the freezer kept at?" returned no passage. The document says "frozen", and the freezer/frozen stem applies only after a passage is already a candidate. Hash embeddings and English full text did not retrieve it.
- "Quote the fee Orry uses for a new lamp oil booking." returned the superseded card. That card says not to use it for a new booking, so the words "new booking" matched the warning. The model then quoted 29 pounds from the passage it was given.

Generation misses where a passage was retrieved:

- The current fee answer was replaced by "I could not confirm that against the company records." The citation check rejected the generated text.
- The store answer stated 7 Beacon Road and 8 drums and left out `ORRY-STORE-8`.
- The superseded-card answer was replaced by the same confirmation refusal.
- The wick procedure was paraphrased as "Orry wick" and did not state `ORRY-WICK-4`. The code sits after a long repeated sentence, so the retrieved chunk can omit it.
- The follow-up "What code is on it?" was replaced by the confirmation refusal.

No acceptance miss was a thousands separator. The formatting scorer recorded zero terms that failed only because of commas, spacing, or a leading zero on a clock.

Representative conversations that stayed factual:

- "What is the account bond and when are invoices due?" — "Account bond: 350 pounds. Invoices due: within 18 days."
- "What are the Sunday opening hours?" — "Sunday receiving is open from 10:30 to 12:30."
- "What does the cover exclude and what is the cover limit?" — "Exclusion: salt spray. Cover limit: 64000 pounds."
- "What is the late-fee percent?" — "5 percent."
- "What is the account bond and what salary does the depot lead earn?" passed the partial check: the labeled bond figure was present and the answer included a refusal for the missing salary. The salary question on its own returned no passage. The exact partial wording was not kept in the transcript.

## Product acceptance

Optimization stops here. The hybrid candidate pool and the answerability stage stay. The Assistant is ready for a personal review with these limits: the fresh-set recall is 0.81, factual correctness under the visitor output cap is 0.50, and a superseded warning can outrank the current card when the question repeats the warning's words. Unsupported salary, address, and telephone questions were rejected from the evidence. Public inference stays disabled.
