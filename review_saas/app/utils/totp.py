import pyotp, base64

    def new_secret() -> str:
        return pyotp.random_base32()

    def totp_now(secret: str) -> str:
        return pyotp.TOTP(secret).now()

    def verify_totp(secret: str, code: str) -> bool:
        try:
            return pyotp.TOTP(secret).verify(code, valid_window=1)
        except Exception:
            return False