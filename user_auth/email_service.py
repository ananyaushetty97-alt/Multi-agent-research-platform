"""
Email delivery service for sending OTP verification and password reset emails.
Supports:
1. Resend API (HTTPS port 443 - bypasses ISP SMTP port blocks)
2. Brevo API (HTTPS port 443 - bypasses ISP SMTP port blocks)
3. Standard SMTP with STARTTLS or SSL (ports 587, 465)
4. Safe in-memory capture with development console fallback ONLY when unconfigured.
"""

import os
import json
import logging
import smtplib
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, List, Dict, Tuple

from user_auth.config import settings

log = logging.getLogger("user_auth.email_service")


class EmailService:
    def __init__(self):
        # In-memory history for test verification
        self.sent_emails: List[Dict[str, str]] = []
        self.last_error: Optional[str] = None

    def send_verification_email(self, to_email: str, name: str, otp: str, verify_link: Optional[str] = None) -> bool:
        """Send 6-digit verification code and optional magic link."""
        subject = f"Your verification code: {otp}"

        # Only print OTPs to the console when ENV=development and email is NOT configured.
        env_mode = (os.getenv("ENV") or os.getenv("APP_ENV") or "development").lower()
        is_dev = env_mode in ("development", "dev", "local", "test") and env_mode != "production"
        if is_dev and not settings.email_configured:
            print(f"\n" + "=" * 60, flush=True)
            print(f"[DEVELOPMENT MODE - EMAIL NOT CONFIGURED] Verification code for {to_email}: {otp}", flush=True)
            if verify_link:
                print(f"[DEVELOPMENT MODE] One-click link: {verify_link}", flush=True)
            print("=" * 60 + "\n", flush=True)

        link_html = ""
        link_text = ""
        if verify_link:
            link_html = f"""
            <p style="margin: 24px 0 8px 0; font-size: 14px; color: #4f6070;">Or verify automatically with this one-click link:</p>
            <p style="margin: 0;"><a href="{verify_link}" style="display: inline-block; padding: 10px 20px; background-color: #005151; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 500; font-size: 14px;">Verify Email Address</a></p>
            """
            link_text = f"\nAlternatively, verify by clicking: {verify_link}\n"

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f7f9ff; margin: 0; padding: 32px 16px; color: #111d28;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #dde9f9; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
    <div style="margin-bottom: 24px; display: flex; align-items: center; gap: 8px;">
      <h2 style="font-size: 20px; font-weight: 600; color: #005151; margin: 0;">Research Hub</h2>
    </div>
    <h1 style="font-size: 22px; font-weight: 600; color: #111d28; margin: 0 0 12px 0;">Your verification code</h1>
    <p style="font-size: 15px; color: #3f4948; line-height: 1.5; margin: 0 0 24px 0;">
      Hello {name}, welcome to Research Hub. Please enter the following 6-digit verification code to activate your account:
    </p>
    <div style="background-color: #edf4ff; border: 1px solid #cfe2f5; border-radius: 8px; padding: 16px 24px; text-align: center; margin-bottom: 24px;">
      <span style="font-family: monospace; font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #005151;">{otp}</span>
    </div>
    <p style="font-size: 13px; color: #6f7979; margin: 0 0 16px 0;">
      This code expires in {settings.otp_expiry_minutes} minutes. If you did not create an account on Research Hub, you can safely ignore this email.
    </p>
    {link_html}
  </div>
</body>
</html>"""

        plain_text = f"""Hello {name},

Your verification code for Research Hub is: {otp}

This code expires in {settings.otp_expiry_minutes} minutes.
{link_text}
If you did not create an account, you can safely ignore this email.
"""
        return self._send(to_email, subject, plain_text, html_body)

    def send_password_reset_email(self, to_email: str, name: str, reset_link: str) -> bool:
        """Send password reset link email."""
        subject = "Reset your Research Hub password"

        env_mode = (os.getenv("ENV") or os.getenv("APP_ENV") or "development").lower()
        is_dev = env_mode in ("development", "dev", "local", "test") and env_mode != "production"
        if is_dev and not settings.email_configured:
            print(f"\n" + "=" * 60, flush=True)
            print(f"[DEVELOPMENT MODE - EMAIL NOT CONFIGURED] Password reset link for {to_email}: {reset_link}", flush=True)
            print("=" * 60 + "\n", flush=True)

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f7f9ff; margin: 0; padding: 32px 16px; color: #111d28;">
  <div style="max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #dde9f9; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
    <div style="margin-bottom: 24px;">
      <h2 style="font-size: 20px; font-weight: 600; color: #005151; margin: 0;">Research Hub</h2>
    </div>
    <h1 style="font-size: 22px; font-weight: 600; color: #111d28; margin: 0 0 12px 0;">Reset your password</h1>
    <p style="font-size: 15px; color: #3f4948; line-height: 1.5; margin: 0 0 24px 0;">
      Hello {name}, we received a request to reset your password. Click the button below to choose a new password:
    </p>
    <div style="text-align: center; margin: 28px 0;">
      <a href="{reset_link}" style="display: inline-block; padding: 12px 28px; background-color: #005151; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 15px;">Reset Password</a>
    </div>
    <p style="font-size: 13px; color: #6f7979; margin: 0 0 12px 0;">
      This link is valid for {settings.reset_token_expiry_minutes} minutes and can only be used once.
    </p>
    <p style="font-size: 13px; color: #6f7979; margin: 0;">
      If you did not request a password reset, please ignore this email. Your password will remain unchanged.
    </p>
  </div>
</body>
</html>"""

        plain_text = f"""Hello {name},

Click the following link to reset your password:
{reset_link}

This link is valid for {settings.reset_token_expiry_minutes} minutes.
If you did not request a password reset, please ignore this email.
"""
        return self._send(to_email, subject, plain_text, html_body)

    def _send(self, to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
        """Internal dispatch via configured email provider (Resend, Brevo, or SMTP)."""
        self.last_error = None
        self.sent_emails.append({
            "to": to_email,
            "subject": subject,
            "text": plain_text,
            "html": html_body,
        })

        # 1. Try Resend API (HTTPS port 443)
        if settings.resend_api_key and settings.resend_api_key.strip():
            return self._send_resend(to_email, subject, plain_text, html_body)

        # 2. Try Brevo API (HTTPS port 443)
        if settings.brevo_api_key and settings.brevo_api_key.strip():
            return self._send_brevo(to_email, subject, plain_text, html_body)

        # 3. Try standard SMTP
        if settings.smtp_host and settings.smtp_host.strip():
            return self._send_smtp(to_email, subject, plain_text, html_body)

        # 4. Fallback when unconfigured: capture in memory (dev/test)
        log.info("Email delivery not configured. Email to %s captured in memory. Subject: %s", to_email, subject)
        return True

    def _send_resend(self, to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
        """Dispatch email via Resend HTTPS API (port 443)."""
        try:
            from_addr = settings.resend_from or "Research Hub <onboarding@resend.dev>"
            payload = {
                "from": from_addr,
                "to": [to_email],
                "subject": subject,
                "text": plain_text,
                "html": html_body,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=data,
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key.strip()}",
                    "Content-Type": "application/json",
                    "User-Agent": "ResearchHub/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=settings.smtp_timeout_seconds) as resp:
                if resp.status in (200, 201):
                    log.info("Email sent to %s successfully via Resend API.", to_email)
                    return True
                self.last_error = f"Resend API returned status {resp.status}"
                log.error("Failed to deliver email to %s via Resend: HTTP %s", to_email, resp.status)
                return False
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            self.last_error = f"Resend API error ({e.code}): {err_body}"
            log.error("Failed to deliver email to %s via Resend API: %s", to_email, self.last_error)
            return False
        except Exception as e:
            self.last_error = f"Resend connection error: {e}"
            log.error("Failed to deliver email to %s via Resend API: %s", to_email, e)
            return False

    def _send_brevo(self, to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
        """Dispatch email via Brevo HTTPS API (port 443)."""
        try:
            from_addr = settings.brevo_from or settings.smtp_from or "devaraddi31@gmail.com"
            payload = {
                "sender": {"name": "Research Hub", "email": from_addr},
                "to": [{"email": to_email}],
                "subject": subject,
                "textContent": plain_text,
                "htmlContent": html_body,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.brevo.com/v3/smtp/email",
                data=data,
                headers={
                    "api-key": settings.brevo_api_key.strip(),
                    "Content-Type": "application/json",
                    "User-Agent": "ResearchHub/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=settings.smtp_timeout_seconds) as resp:
                if resp.status in (200, 201, 202):
                    log.info("Email sent to %s successfully via Brevo API.", to_email)
                    return True
                self.last_error = f"Brevo API returned status {resp.status}"
                log.error("Failed to deliver email to %s via Brevo: HTTP %s", to_email, resp.status)
                return False
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            self.last_error = f"Brevo API error ({e.code}): {err_body}"
            log.error("Failed to deliver email to %s via Brevo API: %s", to_email, self.last_error)
            return False
        except Exception as e:
            self.last_error = f"Brevo connection error: {e}"
            log.error("Failed to deliver email to %s via Brevo API: %s", to_email, e)
            return False

    def _send_smtp(self, to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
        """Dispatch email via standard SMTP."""
        timeout = settings.smtp_timeout_seconds or 5
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.smtp_from
            msg["To"] = to_email

            part1 = MIMEText(plain_text, "plain")
            part2 = MIMEText(html_body, "html")
            msg.attach(part1)
            msg.attach(part2)

            if settings.smtp_port == 465:
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout)
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
                if settings.smtp_tls:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()

            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)

            server.sendmail(settings.smtp_from, [to_email], msg.as_string())
            server.quit()
            log.info("Email sent to %s successfully via SMTP.", to_email)
            return True
        except Exception as e:
            self.last_error = str(e)
            log.error("Failed to deliver email to %s via SMTP: %s", to_email, e)
            return False


email_service = EmailService()
