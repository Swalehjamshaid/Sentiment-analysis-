import pandas as pd
    from pathlib import Path

    def export_reviews(path: str, rows: list[dict], fmt: str = 'csv') -> str:
        df = pd.DataFrame(rows)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if fmt == 'excel':
            out = path if path.endswith('.xlsx') else path + '.xlsx'
            df.to_excel(out, index=False)
            return out
        out = path if path.endswith('.csv') else path + '.csv'
        df.to_csv(out, index=False)
        return out