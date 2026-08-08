import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.llm_extractor import LLMExtractor


@patch("src.llm_extractor.NEW_GENAI_AVAILABLE", False)
@patch("google.generativeai.GenerativeModel")
def test_extract_structured_data_legacy(mock_generative_model):
    # Setup mock response
    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"bank_name": "ملی", "amount": 100000}'
    mock_model_instance.generate_content.return_value = mock_response
    mock_generative_model.return_value = mock_model_instance

    extractor = LLMExtractor(api_key="fake-key", model_name="gemini-3.5-flash")
    
    # Test text-based extraction
    result = extractor.extract_structured_data("Some OCR text")
    assert result == {"bank_name": "ملی", "amount": 100000}


@patch("src.llm_extractor.NEW_GENAI_AVAILABLE", False)
@patch("google.generativeai.GenerativeModel")
@patch("PIL.Image.open")
def test_extract_structured_data_from_image_legacy(mock_image_open, mock_generative_model, tmp_path):
    # Setup mock image file
    fake_image_path = tmp_path / "test_receipt.png"
    fake_image_path.write_bytes(b"fake image data")

    mock_image = MagicMock()
    mock_image_open.return_value = mock_image

    # Setup mock response
    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"bank_name": "ملت", "amount": 50000}'
    mock_model_instance.generate_content.return_value = mock_response
    mock_generative_model.return_value = mock_model_instance

    extractor = LLMExtractor(api_key="fake-key", model_name="gemini-3.5-flash")
    
    # Test multimodal extraction
    result = extractor.extract_structured_data_from_image(fake_image_path)
    assert result == {"bank_name": "ملت", "amount": 50000}
    mock_image_open.assert_called_once_with(fake_image_path)
    mock_model_instance.generate_content.assert_called_once()
