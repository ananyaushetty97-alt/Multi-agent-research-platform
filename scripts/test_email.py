#!/usr/bin/env python3
"""
Diagnostic utility to test email configuration and delivery without starting the web server.
Supports:
  1. Standard SMTP (Gmail, Outlook, etc.)
  2. Resend API (HTTPS port 443 - bypasses ISP port blocks)
  3. Brevo API (HTTPS port 443 - bypasses ISP port blocks)

Usage:
    python scripts/test_email.py [recipient@example.com]
"""

import os
import sys
import json
import socket
import smtplib
import urllib.request
import urllib.error
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_api_delivery(provider: str, api_key: str, recipient: str, sender: str) -> bool:
    print(f"\n[API Delivery Test] Using {provider} over HTTPS (port 443)...")
    subject = "Research Hub - Verification Code: 849201"
    text = "Hello,\n\nThis is a test verification email from Research Hub.\nVerification code: 849201\n\nIf you received this, your email setup is fully operational!"
    html = f"""<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; padding: 20px; background: #f8fafc;">
  <div style="max-width: 480px; margin: auto; background: white; padding: 24px; border-radius: 8px; border: 1px solid #e2e8f0;">
    <h2 style="color: #005151; margin-top: 0;">Research Hub - Verification Test</h2>
    <p>Your email delivery configuration is functioning perfectly!</p>
    <div style="background: #edf4ff; padding: 16px; border-radius: 6px; text-align: center; margin: 20px 0;">
      <span style="font-family: monospace; font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #005151;">849201</span>
    </div>
    <p style="font-size: 13px; color: #64748b;">Delivered via {provider} HTTPS API.</p>
  </div>
</body>
</html>"""

    if provider.lower() == "resend":
        payload = {
            "from": sender or "Research Hub <onboarding@resend.dev>",
            "to": [recipient],
            "subject": subject,
            "text": text,
            "html": html,
        }
        url = "https://api.resend.com/emails"
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "ResearchHub/1.0",
        }
    else:  # Brevo
        payload = {
            "sender": {"name": "Research Hub", "email": sender or "noreply@platform.ai"},
            "to": [{"email": recipient}],
            "subject": subject,
            "textContent": text,
            "htmlContent": html,
        }
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": api_key.strip(),
            "Content-Type": "application/json",
            "User-Agent": "ResearchHub/1.0",
        }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            print(f"      ✅ {provider} accepted delivery request (HTTP {resp.status})!")
            print(f"      🎉 Verification email dispatched to {recipient}!")
            return True
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        print(f"      ❌ {provider} API returned HTTP {e.code}: {err_msg}")
        return False
    except Exception as e:
        print(f"      ❌ {provider} connection error: {e}")
        return False


def run_smtp_test(recipient: str):
    print("=" * 65)
    print("      RESEARCH HUB - EMAIL CONFIGURATION & DELIVERY TEST")
    print("=" * 65)

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("BREVO_FROM") or os.getenv("SMTP_FROM") or "devaraddi31@gmail.com"
    use_tls = os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")

    resend_key = os.getenv("RESEND_API_KEY")
    brevo_key = os.getenv("BREVO_API_KEY")

    print(f"[*] Target Recipient : {recipient}")
    print(f"[*] SMTP Host        : {host or '(NOT CONFIGURED)'}")
    print(f"[*] SMTP Port        : {port}")
    print(f"[*] SMTP User        : {user or '(NONE)'}")
    print(f"[*] SMTP Password    : {'******' if password else '(NONE)'}")
    print(f"[*] SMTP Sender      : {sender}")
    print(f"[*] STARTTLS Enabled : {use_tls}")
    print(f"[*] Resend API Key   : {'******' if resend_key else '(NONE)'}")
    print(f"[*] Brevo API Key    : {'******' if brevo_key else '(NONE)'}")
    print("-" * 65)

    # If Resend API Key is present, test Resend
    if resend_key and resend_key.strip():
        from_addr = os.getenv("RESEND_FROM", "Research Hub <onboarding@resend.dev>")
        success = test_api_delivery("Resend", resend_key, recipient, from_addr)
        if success:
            return

    # If Brevo API Key is present, test Brevo
    if brevo_key and brevo_key.strip():
        from_addr = os.getenv("BREVO_FROM", sender)
        success = test_api_delivery("Brevo", brevo_key, recipient, from_addr)
        if success:
            return

    if not host:
        print("\n❌ ERROR: Neither SMTP nor HTTPS Email API is configured in .env!")
        print("\nTo send verification emails, you have two choices:")
        print("Choice 1: HTTPS API (Works through all firewalls/ISPs without port blocks)")
        print("  RESEND_API_KEY=re_your_api_key")
        print("Choice 2: Gmail SMTP")
        print("  SMTP_HOST=smtp.gmail.com")
        print("  SMTP_PORT=587")
        print("  SMTP_USER=your-email@gmail.com")
        print("  SMTP_PASSWORD=your-16-character-app-password")
        print("  SMTP_FROM=your-email@gmail.com")
        sys.exit(1)

    print(f"\n[1/4] Connecting to {host}:{port} (timeout 5s)...")
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=5)
        else:
            server = smtplib.SMTP(host, port, timeout=5)
        print("      ✅ Connected successfully.")
    except Exception as e:
        print(f"      ❌ Connection failed: {e}")
        print("\n🔎 DIAGNOSIS:")
        if "timed out" in str(e).lower() or isinstance(e, (socket.timeout, TimeoutError)):
            print("   Connection timed out connecting to SMTP port 587 / 465.")
            print("   Root cause: Your ISP or network firewall blocks outbound SMTP ports (587/465).")
            print("   RECOMMENDED FIX: Configure RESEND_API_KEY or BREVO_API_KEY in .env.")
            print("   HTTPS APIs run over port 443, which is 100% open and unblocked.")
        sys.exit(1)

    print("[2/4] Initializing EHLO and STARTTLS...")
    try:
        if port != 465:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
                print("      ✅ STARTTLS negotiation successful.")
            else:
                print("      ⚠️  STARTTLS skipped as configured.")
    except Exception as e:
        print(f"      ❌ STARTTLS failed: {e}")
        try:
            server.quit()
        except Exception:
            pass
        sys.exit(1)

    if user and password:
        print(f"[3/4] Authenticating as {user}...")
        try:
            server.login(user, password)
            print("      ✅ Authentication successful.")
        except smtplib.SMTPAuthenticationError as e:
            print(f"      ❌ Authentication failed (535): {e}")
            print("\n💡 TIP For Gmail Users:")
            print("   You must use a Google 16-character 'App Password', NOT your standard Gmail password.")
            print("   Visit: https://myaccount.google.com/apppasswords")
            try:
                server.quit()
            except Exception:
                pass
            sys.exit(1)
        except Exception as e:
            print(f"      ❌ Authentication error: {e}")
            try:
                server.quit()
            except Exception:
                pass
            sys.exit(1)
    else:
        print("[3/4] Skipping authentication (no credentials provided).")

    print(f"[4/4] Sending test verification email to {recipient}...")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your verification code: 849201"
        msg["From"] = sender
        msg["To"] = recipient

        text = "Hello,\n\nThis is a test verification email from Research Hub.\nVerification code: 849201\n\nIf you received this, your SMTP setup is fully functional!"
        html = """<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; padding: 20px; background: #f8fafc;">
  <div style="max-width: 480px; margin: auto; background: white; padding: 24px; border-radius: 8px; border: 1px solid #e2e8f0;">
    <h2 style="color: #005151; margin-top: 0;">Research Hub - SMTP Test</h2>
    <p>Your SMTP email configuration is functioning perfectly!</p>
    <div style="background: #edf4ff; padding: 16px; border-radius: 6px; text-align: center; margin: 20px 0;">
      <span style="font-family: monospace; font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #005151;">849201</span>
    </div>
    <p style="font-size: 13px; color: #64748b;">This was sent by scripts/test_email.py.</p>
  </div>
</body>
</html>"""
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        server.sendmail(sender, [recipient], msg.as_string())
        server.quit()
        print(f"      ✅ Test email sent to {recipient} successfully!")
        print("\n🎉 SUCCESS: Your email configuration is verified and ready for production.")
        print("=" * 65)
    except Exception as e:
        print(f"      ❌ Failed to send message: {e}")
        try:
            server.quit()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SMTP_USER", "test@example.com")
    run_smtp_test(target)
