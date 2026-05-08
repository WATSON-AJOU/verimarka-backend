from config.middleware import normalize_request_id


def test_normalize_request_id_accepts_safe_client_value():
    request_id = "client-REQ_123.trace:01"

    assert normalize_request_id(request_id) == request_id


def test_normalize_request_id_replaces_control_characters():
    request_id = normalize_request_id("client-id\nforged-log-line")

    assert request_id != "client-id\nforged-log-line"
    assert len(request_id) == 32
    assert request_id.isalnum()


def test_normalize_request_id_replaces_oversized_value():
    request_id = normalize_request_id("a" * 129)

    assert request_id != "a" * 129
    assert len(request_id) == 32
    assert request_id.isalnum()
