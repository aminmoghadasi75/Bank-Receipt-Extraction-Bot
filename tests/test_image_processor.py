import numpy as np
import pytest
from src.image_processor import ImageProcessor


def test_image_processor_preprocessing():
    processor = ImageProcessor()
    # Create a synthetic 100x100 BGR dummy image
    dummy_image = np.zeros((100, 100, 3), dtype=np.uint8)
    processed = processor.preprocess(dummy_image)

    assert isinstance(processed, np.ndarray)
    assert processed.shape == (100, 100, 3)


def test_image_processor_invalid_path():
    processor = ImageProcessor()
    with pytest.raises(FileNotFoundError):
        processor.preprocess("non_existent_file_path.png")
