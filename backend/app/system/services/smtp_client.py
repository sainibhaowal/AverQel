from __future__ import annotations

import smtplib
import ssl
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import Settings


@contextmanager
def smtp_connection(settings: Settings, *, timeout: float) -> Iterator[smtplib.SMTP]:
    """Open an SMTP session using the configured encrypted transport."""
    host = settings.notification_smtp_host
    if not host:
        raise RuntimeError("SMTP host is not configured")

    tls_context = ssl.create_default_context()
    if settings.notification_smtp_implicit_tls:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            host,
            settings.notification_smtp_port,
            timeout=timeout,
            context=tls_context,
        )
    else:
        client = smtplib.SMTP(host, settings.notification_smtp_port, timeout=timeout)

    with client:
        client.ehlo()
        if settings.notification_smtp_starttls:
            client.starttls(context=tls_context)
            client.ehlo()
        yield client
