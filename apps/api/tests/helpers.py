from fastapi.testclient import TestClient


def login(client: TestClient, email: str, password: str) -> dict[str, object]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    payload: dict[str, object] = response.json()
    return payload
