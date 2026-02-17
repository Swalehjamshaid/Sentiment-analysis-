import bleach

    def clean_html(text: str) -> str:
        return bleach.clean(text or "", tags=[], attributes={}, protocols=[], strip=True)