import pandas as pd
    from pathlib import Path

    def save_kpis_to_xlsx(path: str, kpis: dict):
        df = pd.DataFrame([kpis])
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(path, index=False)
        return path