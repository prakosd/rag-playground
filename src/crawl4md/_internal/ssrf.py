"""Opt-in SSRF guard: refuse crawl/download targets on internal networks.

Enabled via :attr:`crawl4md.config.CrawlerConfig.block_private_networks`.
:func:`url_targets_blocked_network` resolves a URL's host and reports whether any resolved
address is loopback, private, link-local, reserved, multicast, or unspecified — which covers
the cloud-metadata endpoints (``169.254.169.254`` / ``169.254.170.2`` are link-local). A
resolution failure returns ``False`` so the normal fetch path surfaces the error; only a
confirmed internal address blocks. Pure stdlib (no project imports).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

__all__ = ["BLOCKED_NETWORK_REASON", "BlockedNetworkError", "url_targets_blocked_network"]

# Reason recorded on a blocked page/download (the CrawlResult already carries the URL).
BLOCKED_NETWORK_REASON = "target resolves to a private or internal network address"


class BlockedNetworkError(Exception):
    """Raised by the fetch path when the SSRF guard refuses an internal-network target."""


def url_targets_blocked_network(url: str) -> bool:
    """Return ``True`` if *url*'s host resolves to a non-public (internal) address."""
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False  # unresolvable — let the normal fetch fail and report it
    for info in infos:
        address = info[4][0].split("%", 1)[0]  # drop any IPv6 scope id (e.g. fe80::1%eth0)
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False
