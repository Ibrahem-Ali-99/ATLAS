from app.scripts.provision_embedding import (
    PINNED_OLLAMA_MODEL,
    EmbeddingProvisionError,
    model_is_present,
    ollama_root,
    parse_model_names,
    provision,
    vector_width,
)


class FakeClient:
    def __init__(self, names: list[str], width: int = 768) -> None:
        self.names = list(names)
        self.width = width
        self.pulls: list[str] = []
        self.inputs: list[list[str]] = []

    def get_json(self, url: str) -> dict[str, object]:
        assert url.endswith("/api/tags")
        return {"models": [{"name": name} for name in self.names]}

    def post_json(self, url: str, body: dict[str, object]) -> dict[str, object]:
        if url.endswith("/api/pull"):
            name = str(body["name"])
            self.pulls.append(name)
            self.names.append(name)
            return {"status": "success"}
        values = body["input"]
        assert isinstance(values, list)
        texts = [str(value) for value in values]
        self.inputs.append(texts)
        if texts and texts[0].startswith("Which invoice"):
            rows = [
                [1.0, 0.0],
                [0.9, 0.1],
                [0.0, 1.0],
            ]
        else:
            rows = [[1.0, 0.0] for _text in texts]
        return {"data": [{"embedding": (row + [0.0] * self.width)[: self.width]} for row in rows]}


def test_installed_model_is_not_pulled_again() -> None:
    client = FakeClient([PINNED_OLLAMA_MODEL])
    line = provision(
        provider="ollama",
        base_url="http://ollama:11434/v1",
        model=PINNED_OLLAMA_MODEL,
        dimensions=768,
        client=client,
    )
    assert client.pulls == []
    assert "pulled=false" in line
    assert "width=768" in line


def test_missing_model_is_pulled_once_and_checked() -> None:
    client = FakeClient([])
    line = provision(
        provider="ollama",
        base_url="http://ollama:11434/v1",
        model=PINNED_OLLAMA_MODEL,
        dimensions=768,
        client=client,
    )
    assert client.pulls == [PINNED_OLLAMA_MODEL]
    assert "pulled=true" in line
    assert len(client.inputs) == 3


def test_wrong_width_fails_before_a_chunk_is_stored() -> None:
    client = FakeClient([PINNED_OLLAMA_MODEL], width=1536)
    try:
        provision(
            provider="ollama",
            base_url="http://ollama:11434/v1",
            model=PINNED_OLLAMA_MODEL,
            dimensions=768,
            client=client,
        )
    except EmbeddingProvisionError as exc:
        assert exc.reason == "embedding_dimension_mismatch width=1536 expected=768"
    else:
        raise AssertionError("expected a dimension mismatch")


def test_openai_path_skips_ollama() -> None:
    client = FakeClient([])
    line = provision(
        provider="openai",
        base_url="https://api.openai.com/v1",
        model="text-embedding-3-small",
        dimensions=1536,
        client=client,
    )
    assert line == "embedding_skipped provider=openai dimensions=1536"
    assert client.pulls == []
    assert client.inputs == []


def test_unreachable_ollama_reports_a_stable_reason() -> None:
    class Down:
        def get_json(self, url: str) -> dict[str, object]:
            raise EmbeddingProvisionError(
                "embedding_unavailable Ollama is not running at the configured address."
            )

        def post_json(self, url: str, body: dict[str, object]) -> dict[str, object]:
            raise AssertionError("pull should not run")

    try:
        provision(
            provider="ollama",
            base_url="http://ollama:11434/v1",
            model=PINNED_OLLAMA_MODEL,
            dimensions=768,
            client=Down(),
        )
    except EmbeddingProvisionError as exc:
        assert exc.reason.startswith("embedding_unavailable")
    else:
        raise AssertionError("expected an unavailable model")


def test_tag_parsing_matches_the_pinned_name() -> None:
    assert ollama_root("http://ollama:11434/v1") == "http://ollama:11434"
    names = parse_model_names({"models": [{"name": PINNED_OLLAMA_MODEL}]})
    assert model_is_present(names, PINNED_OLLAMA_MODEL)
    assert not model_is_present(names, "nomic-embed-text")
    assert vector_width({"data": [{"embedding": [0.1, 0.2]}]}) == 2
