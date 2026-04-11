import resend
import os
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

# Railway Configuration
resend.api_key = os.getenv("RESEND_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM", "onboarding@resend.dev")
BASE_URL = os.getenv("APP_BASE_URL", "https://sentiment-analysis-production-f96a.up.railway.app")

async def send_verification_email(email: str, token: str):
    """Sends the Magic Link via Resend API."""
    verify_url = f"{BASE_URL}/api/auth/verify?token={token}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f9fafb;">
        <div style="max-width: 600px; margin: auto; background: white; padding: 40px; border-radius: 12px; border: 1px solid #e5e7eb; text-align: center;">
            <h2 style="color: #4f46e5;">Review Intel AI</h2>
            <p style="color: #374151; font-size: 16px;">Welcome! Click the button below to verify your email and log in to your dashboard instantly.</p>
            <div style="margin: 30px 0;">
                <a href="{verify_url}" 
                   style="background-color: #4f46e5; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">
                   Verify & Login
                </a>
            </div>
            <p style="color: #6b7280; font-size: 12px;">This link will expire in 30 minutes. If you didn't create an account, ignore this email.</p>
        </div>
    </body>
    </html>
    """

    try:
        resend.Emails.send({
            "from": f"Review Intel AI <{MAIL_FROM}>",
            "to": [email],
            "subject": "Your Magic Login Link - Review Intel AI",
            "html": html_content
        })
        print(f"SUCCESS: Email sent to {email}")
        return True
    except Exception as e:
        print(f"RESEND ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail="Mail service unavailable.")
