"""Bounded SMTP connection verification without sending a message."""

import smtplib
import ssl
from dataclasses import dataclass


@dataclass(frozen=True)
class SmtpVerification:
    verified: bool
    detail: str


def verify_smtp(
    *,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    starttls: bool,
    use_tls: bool,
    timeout: float = 5,
) -> SmtpVerification:
    if username or password:
        if not username or not password:
            return SmtpVerification(False, "SMTP username and password must be supplied together.")
        if not starttls and not use_tls:
            return SmtpVerification(
                False, "Select TLS or STARTTLS before testing SMTP credentials."
            )
    try:
        context = ssl.create_default_context()
        client: smtplib.SMTP | smtplib.SMTP_SSL
        if use_tls:
            client = smtplib.SMTP_SSL(host, port, timeout=timeout, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=timeout)
        with client:
            if starttls:
                client.starttls(context=context)
            if username and password:
                client.login(username, password)
        return SmtpVerification(
            True,
            "SMTP connection and authentication succeeded. "
            "Sender identity still requires provider verification.",
        )
    except smtplib.SMTPAuthenticationError:
        return SmtpVerification(False, "SMTP authentication failed.")
    except smtplib.SMTPServerDisconnected as exc:
        return SmtpVerification(
            False,
            f"SMTP server disconnected during verification ({type(exc).__name__}).",
        )
    except (smtplib.SMTPException, ssl.SSLError) as exc:
        return SmtpVerification(
            False,
            f"SMTP TLS or protocol verification failed ({type(exc).__name__}).",
        )
    except TimeoutError:
        return SmtpVerification(False, "SMTP verification timed out.")
    except OSError as exc:
        return SmtpVerification(False, f"SMTP connection failed ({type(exc).__name__}).")
