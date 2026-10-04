import pytest
from unittest.mock import patch, MagicMock
from llm.parser import parse_requirements

@patch('llm.parser.get_client')
@patch('time.sleep', return_value=None)  # Mock sleep so tests run fast
def test_503_retry_success(mock_sleep, mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    
    # 503 fails twice, succeeds third time
    mock_response = MagicMock()
    mock_response.text = '{"plot": {"width": 40, "depth": 50, "unit": "ft", "facing": "east"}, "rooms": {"bedroom": 2}, "parking": true, "vastu_enabled": false}'
    
    mock_client.models.generate_content.side_effect = [
        Exception("503 UNAVAILABLE"),
        Exception("503 UNAVAILABLE"),
        mock_response
    ]
    
    reqs = parse_requirements("I have 40x50 land. 2 bedrooms.")
    
    assert reqs.plot.width == 40
    assert mock_client.models.generate_content.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(2) # First retry base_delay
    mock_sleep.assert_any_call(4) # Second retry base_delay * 2

@patch('llm.parser.get_client')
@patch('time.sleep', return_value=None)
def test_503_retry_failure(mock_sleep, mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    
    # Always fails with 503
    mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE")
    
    with pytest.raises(ValueError, match="Gemini is temporarily busy"):
        parse_requirements("I have 40x50 land. 2 bedrooms.")
        
    assert mock_client.models.generate_content.call_count == 3 # 3 attempts
    assert mock_sleep.call_count == 2

@patch('llm.parser.get_client')
@patch('time.sleep', return_value=None)
def test_429_no_retry(mock_sleep, mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    
    # Fails with 429
    mock_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")
    
    with pytest.raises(ValueError, match="Gemini API quota/rate limit has been exceeded"):
        parse_requirements("I have 40x50 land. 2 bedrooms.")
        
    assert mock_client.models.generate_content.call_count == 1 # No retries
    assert mock_sleep.call_count == 0
