# app/services/exports.py

from typing import List, Dict
import pandas as pd
from io import BytesIO

def export_reviews_report(reviews: List[Dict], file_format: str = "xlsx") -> BytesIO:
    """
    Export reviews data to an Excel or CSV file in memory.
    """
    df = pd.DataFrame(reviews)
    output = BytesIO()
    
    if file_format.lower() == "xlsx":
        df.to_excel(output, index=False, engine='openpyxl')
    elif file_format.lower() == "csv":
        df.to_csv(output, index=False)
    else:
        raise ValueError("Unsupported file format: choose 'xlsx' or 'csv'")
    
    output.seek(0)
    return output
