import sys
import argparse
from pathlib import Path
from typing import List
from loguru import logger

from config.settings import INPUT_DIR, OUTPUT_DIR
from src.image_processor import ImageProcessor
from src.ocr_engine import OCREngine
from src.llm_extractor import LLMExtractor
from src.validator import ReceiptValidator
from src.excel_writer import ExcelExporter
from src.schemas import ReceiptData


def configure_logger():
    """Configure loguru format and output level."""
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{message}</cyan>",
        level="INFO"
    )


def process_batch(
    input_dir: Path = INPUT_DIR,
    output_dir: Path = OUTPUT_DIR
) -> Path:
    """Run full extraction pipeline on image files inside input_dir."""
    logger.info("Starting Iranian Bank Receipt Extraction Pipeline with Gemini Gateway...")

    supported_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    image_paths = [
        p for p in Path(input_dir).iterdir()
        if p.is_file() and p.suffix.lower() in supported_extensions
    ]

    if not image_paths:
        logger.warning(f"No image files found in input directory: {input_dir}")
        logger.info("Place receipt images (.jpg, .png, .jpeg) in 'data/input/' and rerun.")
        exporter = ExcelExporter(output_dir=output_dir)
        return exporter.export([])

    logger.info(f"Found {len(image_paths)} receipt image(s) to process in '{input_dir}'.")

    image_processor = ImageProcessor()
    ocr_engine = OCREngine()
    llm_extractor = LLMExtractor()
    validator = ReceiptValidator()
    exporter = ExcelExporter(output_dir=output_dir)

    validated_receipts: List[ReceiptData] = []

    import time
    for idx, img_path in enumerate(image_paths, start=1):
        logger.info(f"[{idx}/{len(image_paths)}] Processing receipt: '{img_path.name}'...")
        try:
            raw_json = {}
            extracted_via_multimodal = False

            try:
                raw_json = llm_extractor.extract_structured_data_from_image(img_path)
                if raw_json and any(v is not None for v in raw_json.values()):
                    extracted_via_multimodal = True
                    logger.info(f"[{img_path.name}] Extracted via Gemini Multimodal Gateway.")
            except Exception as multimodal_err:
                logger.warning(
                    f"[{img_path.name}] Gemini Multimodal API error ({multimodal_err}). "
                    "Falling back to Local OCR pipeline..."
                )

            if not extracted_via_multimodal:
                logger.info(f"[{img_path.name}] Running local OCR fallback pipeline...")
                processed_img = image_processor.preprocess(img_path)
                ocr_text = ocr_engine.extract_text(processed_img)

                if ocr_text.strip():
                    from src.local_extractor import LocalRegexExtractor
                    local_extractor = LocalRegexExtractor()
                    raw_json = local_extractor.extract_structured_data(ocr_text)
                    logger.info(f"[{img_path.name}] Extracted via Local Regex Rule Engine.")
                else:
                    logger.warning(f"[{img_path.name}] Local OCR returned empty text.")

            if raw_json and any(v is not None for v in raw_json.values()):
                receipt = validator.validate(raw_json)
                validated_receipts.append(receipt)

                review_str = " [Needs Manual Review]" if receipt.requires_manual_review else ""
                logger.success(
                    f"[{img_path.name}] [Success] Bank: '{receipt.source_bank}', "
                    f"Amount: {receipt.amount}, Tracking: '{receipt.tracking_id}'{review_str}"
                )
            else:
                logger.error(f"[{img_path.name}] Could not extract any valid data from receipt image.")

        except Exception as e:
            logger.error(f"[{img_path.name}] Pipeline failed: {e}")

        if idx < len(image_paths):
            time.sleep(1)

    export_filepath = exporter.export(validated_receipts)
    logger.success(f"Pipeline completed successfully! Results written to: {export_filepath}")
    return export_filepath


def run_api_server(host: str = "0.0.0.0", port: int = 8000):
    """Start FastAPI Uvicorn Server bridging WhatsApp Bot to Gemini API & SQLite DB."""
    import uvicorn
    logger.info(f"Starting Bank Receipt Extraction FastAPI Server on http://{host}:{port}...")
    uvicorn.run(
        "receipt_api.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Iranian Bank Receipt Extraction Bot & API Server"
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run batch processing mode on local input directory instead of starting FastAPI API server"
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=str(INPUT_DIR),
        help="Path to directory containing receipt images for batch mode (default: data/input)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(OUTPUT_DIR),
        help="Path to directory where Excel files will be saved in batch mode (default: data/output)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="API server bind host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API server bind port (default: 8000)"
    )

    args = parser.parse_args()
    configure_logger()

    if args.batch:
        process_batch(input_dir=Path(args.input_dir), output_dir=Path(args.output_dir))
    else:
        run_api_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
