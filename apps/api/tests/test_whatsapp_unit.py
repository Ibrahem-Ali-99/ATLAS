from app.integrations.whatsapp import parse_cloud_webhook


def test_meta_cloud_envelope_extracts_text_and_status_events() -> None:
    messages, statuses = parse_cloud_webhook(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "phone-1"},
                                "messages": [
                                    {
                                        "id": "wamid.1",
                                        "from": "15551234567",
                                        "type": "text",
                                        "text": {"body": "Hello"},
                                    },
                                    {"id": "ignored", "from": "15551234567", "type": "image"},
                                ],
                                "statuses": [{"id": "wamid.out", "status": "delivered"}],
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert messages == [
        {"id": "wamid.1", "sender": "15551234567", "body": "Hello", "phone_number_id": "phone-1"}
    ]
    assert statuses == [{"id": "wamid.out", "status": "delivered", "phone_number_id": "phone-1"}]


def test_meta_cloud_parser_ignores_malformed_or_unsupported_messages() -> None:
    messages, statuses = parse_cloud_webhook(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [{"type": "text", "id": "x", "text": {"body": " "}}],
                                "statuses": [{}],
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert messages == []
    assert statuses == []
