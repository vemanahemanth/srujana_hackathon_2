import pytest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch
from fragility_engine.sdk import Client, ExternalConnectivityClient

def test_sdk_client_timeout_and_retries_configured():
    client = Client(timeout=15.0, max_retries=5)
    assert client.external.timeout == 15.0
    assert client.external.max_retries == 5

def test_sdk_does_not_retry_400_client_errors():
    ext = ExternalConnectivityClient(api_url="http://mock-api.internal", timeout=5.0, max_retries=3)
    req = urllib.request.Request("http://mock-api.internal/api/ingest/runs")
    
    mock_err = urllib.error.HTTPError("http://mock-api.internal", 422, "Unprocessable Entity", {}, None)
    
    with patch("urllib.request.urlopen", side_effect=mock_err) as mock_urlopen:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            ext._execute_request(req, is_idempotent=True)
        assert exc_info.value.code == 422
        # Must only call ONCE, never retry 4xx errors
        assert mock_urlopen.call_count == 1

def test_sdk_retries_502_on_idempotent_calls():
    ext = ExternalConnectivityClient(api_url="http://mock-api.internal", timeout=5.0, max_retries=3)
    req = urllib.request.Request("http://mock-api.internal/api/ingest/runs/run_01")
    
    mock_err = urllib.error.HTTPError("http://mock-api.internal", 502, "Bad Gateway", {}, None)
    mock_success = MagicMock()
    mock_success.__enter__.return_value.read.return_value = b"{\"status\": \"ok\"}"
    
    with patch("urllib.request.urlopen", side_effect=[mock_err, mock_success]) as mock_urlopen:
        raw = ext._execute_request(req, is_idempotent=True)
        assert b"ok" in raw
        assert mock_urlopen.call_count == 2
