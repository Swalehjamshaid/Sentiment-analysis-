import resend
import os
from fastapi import HTTPException
from dotenv import load_dotenv

# Load environment variables (useful for local testing, 
# though Railway injects them automatically)
load_dotenv()

# Configuration from Railway Environment Variables
# RESEND_API_KEY must be the re_... key you generated
resend.api_key = os.getenv("RESEND_API_KEY")

# MAIL_FROM should be 'onboarding@resend.dev' for testing 
# or your verified domain for production
MAIL_FROM = os.getenv("MAIL_FROM", "onboarding@resend.dev")

# APP_BASE_URL is used to build the verification link
BASE_URL = os.getenv("APP_BASE_URL", "https://sentiment-analysis-production-f96a.up.railway.app")

async def send_verification_email(email: str, token: str):
    """
    Sends a Magic Link verification email via the Resend REST API.
    
    Args:
        email (str): The recipient's email address.
        token (str): The unique JWT verification token.
        
    Returns:
        bool: True if the email was sent successfully.
        
    Raises:
        HTTPException: If the Resend API returns an error or fails.
    """
    
    # Construct the full Magic Link URL
    verify_url = f"{BASE_URL}/api/auth/verify?token={token}"

    # Define the Professional HTML Body
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            .container {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 600px;
                margin: 0 auto;
                padding: 40px 20px;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                text-align: center;
                color: #1f2937;
            }}
            .button {{
                background-color: #4f46e5;
                color: #ffffff !important;
                padding: 16px 32px;
                text-decoration: none;
                border-radius: 8px;
                font-weight: bold;
                display: inline-block;
                margin: 30px 0;
            }}
            .footer {{
                font-size: 12px;
                color: #6b7280;
                margin-top: 40px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1 style="color: #4f46e5;">Review Intel AI</h1>
            <h2>Verify your email address</h2>
            <p>Welcome! You're one step away from accessing your sentiment analysis dashboard. Click the button below to confirm your email and log in immediately.</p>
            
            <a href="{verify_url}" class="button">Verify & Login Now</a>
            
            <p>If the button doesn't work, copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #4f46e5; font-size: 14px;">{verify_url}</p>
            
            <div class="footer">
                <p>This magic link will expire in 60 minutes.</p>
                <p>If you did not create an account, you can safely ignore this email.</p>
            </div>
        </div>
    </body>
    </html>
    """

    try:
        # Trigger the Resend API call
        response = resend.Emails.send({
            "from": f"Review Intel AI <{MAIL_FROM}>",
            "to": [email],
            "subject": "Action Required: Verify Your SaaS Account",
            "html": html_content
        })
        
        # Log the success in Railway Deploy Logs
        print(f"Email successfully sent to {email}. Resend ID: {response.get('id')}")
        return True

    except Exception as e:
        # Catch and log specific errors for debugging in Railway
        print(f"CRITICAL MAILER ERROR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The email service is currently unavailable. Please try again later."
        )
