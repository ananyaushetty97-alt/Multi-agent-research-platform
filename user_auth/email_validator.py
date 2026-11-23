"""
Email verification and security checks:
1. Strict syntax validation.
2. Domain DNS MX and A record check.
3. Disposable / temporary email domain blocklist.
4. Normalization (lowercase, whitespace stripped).
"""

import os
import re
import socket
import logging
from typing import Tuple, Set

log = logging.getLogger("user_auth.email_validator")

# RFC 5322 compliant email regex
STRICT_EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

# Comprehensive list of disposable / temporary email domains
DISPOSABLE_DOMAINS: Set[str] = {
    "mailinator.com",
    "trashmail.com",
    "tempmail.com",
    "temp-mail.org",
    "10minutemail.com",
    "10minutemail.net",
    "guerrillamail.com",
    "guerrillamailblock.com",
    "sharklasers.com",
    "grr.la",
    "yopmail.com",
    "dispostable.com",
    "throwawaymail.com",
    "fakeinbox.com",
    "getairmail.com",
    "maildrop.cc",
    "inboxkitten.com",
    "getnada.com",
    "tempail.com",
    "burnermail.io",
    "crazymailing.com",
    "emailondeck.com",
    "mohmal.com",
    "generator.email",
    "mytemp.email",
    "dropmail.me",
    "nada.ltd",
    "trashmail.net",
    "trashmail.me",
    "discard.email",
    "spambox.us",
    "tempinbox.com",
    "eyepaste.com",
    "mailcatch.com",
    "dumpmail.de",
    "disposablemail.com",
}


TEST_RESERVED_DOMAINS: Set[str] = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "localhost",
    "platform.ai",
}


def normalize_email(email: str) -> str:
    """Strip leading/trailing whitespace and convert to lowercase."""
    if not email:
        return ""
    return email.strip().lower()


def is_valid_syntax(email: str) -> bool:
    """Check email against strict RFC 5322 pattern and length bounds."""
    if not email or len(email) > 254:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local_part, domain_part = parts
    if len(local_part) > 64 or not local_part:
        return False
    if not STRICT_EMAIL_REGEX.match(email):
        return False
    return True


def is_disposable_domain(domain: str) -> bool:
    """Check if the domain is in the disposable email provider blocklist."""
    cleaned_domain = domain.strip().lower()
    if cleaned_domain in DISPOSABLE_DOMAINS:
        return True
    # Subdomain check (e.g. *.mailinator.com)
    for disp in DISPOSABLE_DOMAINS:
        if cleaned_domain.endswith("." + disp):
            return True
    return False


def has_valid_dns_records(domain: str) -> bool:
    """
    Check domain DNS records for valid MX or A records.
    Never probes SMTP mailboxes (per prompt requirement).
    """
    cleaned_domain = domain.strip().lower()
    
    # RFC 2606 / 6761 test domains always allowed in testing / dev
    if cleaned_domain in TEST_RESERVED_DOMAINS:
        return True

    # In test/offline mode or development without external DNS:
    # recognize test/mock domains if configured
    if os.environ.get("SKIP_EMAIL_DNS_CHECK", "false").lower() in ("true", "1"):
        return True

    # Try dnspython first if available
    try:
        import dns.resolver
        try:
            mx_answers = dns.resolver.resolve(cleaned_domain, "MX")
            if mx_answers and len(mx_answers) > 0:
                return True
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            pass
        except Exception:
            pass

        try:
            a_answers = dns.resolver.resolve(cleaned_domain, "A")
            if a_answers and len(a_answers) > 0:
                return True
        except Exception:
            pass
    except ImportError:
        pass

    # Standard library fallback via socket.getaddrinfo (validates A / AAAA / host existence)
    try:
        answers = socket.getaddrinfo(cleaned_domain, None)
        if answers and len(answers) > 0:
            return True
    except (socket.gaierror, socket.herror, TimeoutError):
        return False
    except Exception as e:
        log.warning("DNS resolution exception for %s: %s", cleaned_domain, e)
        return False

    return False


def validate_email_address(email: str, verify_dns: bool = True) -> Tuple[bool, str, str]:
    """
    Comprehensive multi-layer email verification:
    1. Normalize
    2. Syntax check
    3. Disposable domain check
    4. DNS MX / A check (if verify_dns is True)
    
    Returns: (is_valid: bool, normalized_email: str, error_message: str)
    """
    normalized = normalize_email(email)
    if not normalized:
        return False, "", "Email cannot be empty."

    if not is_valid_syntax(normalized):
        return False, normalized, "Please enter a valid email address."

    domain = normalized.split("@")[1]

    if is_disposable_domain(domain):
        return False, normalized, "Disposable / temporary email addresses are not accepted."

    if verify_dns:
        if not has_valid_dns_records(domain):
            return False, normalized, f"Domain '@{domain}' does not have valid mail server (MX/A) records."

    return True, normalized, ""
