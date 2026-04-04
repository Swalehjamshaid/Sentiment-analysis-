import smtplib
from email.message import EmailMessage
from app.core.config import settings

async def send_verification_email(email: str, token: str):
    """Sends an async-compatible SMTP email with the verification link."""
    # Ensure settings.DOMAIN is set to your base URL (e.g., http://localhost:8000)
    verify_url = f"{settings.DOMAIN}/api/auth/verify?token={token}"
    
    msg = EmailMessage()
    msg["Subject"] = "Action Required: Verify Your SaaS Account"
    msg["From"] = settings.SMTP_USER
    msg["To"] = email
    
    # Text-only fallback
    msg.set_content(f"Welcome! Please verify your email by clicking this link: {verify_url}")
    
    # Professional HTML Body
    msg.add_alternative(f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; text-align: center;">
            <div style="max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee;">
                <h2 style="color: #4F46E5;">Welcome to Review Intel!</h2>
                <p>You're almost there. Click the button below to verify your email address and access your dashboard.</p>
                <div style="margin: 30px 0;">
                    <a href="{verify_url}" 
                       style="background-color: #4F46E5; color: white; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                       Verify My Account
                    </a>
                </div>
                <p style="font-size: 0.8em; color: #777;">This link will expire in 30 minutes.</p>
            </div>
        </body>
    </html>
    """, subtype='html')

    try:
        # Standard SMTP logic (works well with Gmail App Passwords)
        with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email Failed: {e}")
        return False
