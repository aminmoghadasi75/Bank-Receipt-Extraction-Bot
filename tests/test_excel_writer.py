import pandas as pd
from src.excel_writer import ExcelExporter
from src.schemas import ReceiptData


def test_excel_exporter(tmp_path):
    exporter = ExcelExporter(output_dir=tmp_path)
    receipt1 = ReceiptData(
        bank_name="پاسارگاد",
        amount=250000,
        tracking_number="778899"
    )
    saved_file = exporter.export([receipt1])

    assert saved_file.exists()
    df = pd.read_excel(saved_file)
    assert len(df) == 1
    assert df.iloc[0]["bank_name"] == "پاسارگاد"
    assert df.iloc[0]["amount"] == 250000
