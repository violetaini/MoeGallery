import ipaddress
from functools import lru_cache

from fastapi import Request

from app.config import settings


TRUSTED_CLIENT_IP_HEADERS = (
    "ali-real-client-ip",
    "ali-cdn-real-ip",
    "true-client-ip",
)


def _parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    raw = (value or "").strip().strip('"')
    if not raw:
        return None
    if raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.index("]")]
    elif raw.count(":") == 1 and "." in raw:
        host, port = raw.rsplit(":", 1)
        if port.isdigit():
            raw = host
    try:
        return ipaddress.ip_address(raw)
    except ValueError:
        return None


@lru_cache(maxsize=32)
def _trusted_proxy_networks(value: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks = []
    for raw_cidr in value.replace(";", ",").split(","):
        cidr = raw_cidr.strip()
        if cidr:
            networks.append(ipaddress.ip_network(cidr, strict=False))
    return tuple(networks)


def _is_trusted_proxy(address: ipaddress.IPv4Address | ipaddress.IPv6Address | None) -> bool:
    if address is None:
        return False
    return any(address in network for network in _trusted_proxy_networks(settings.trusted_proxy_cidrs))


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client and request.client.host else "unknown"
    peer_ip = _parse_ip(peer)
    if _is_trusted_proxy(peer_ip):
        for header_name in TRUSTED_CLIENT_IP_HEADERS:
            header_ip = _parse_ip(request.headers.get(header_name))
            if header_ip:
                return str(header_ip)
        forwarded = request.headers.get("x-forwarded-for", "")
        for raw_part in reversed(forwarded.split(",")):
            forwarded_ip = _parse_ip(raw_part)
            if forwarded_ip and not _is_trusted_proxy(forwarded_ip):
                return str(forwarded_ip)
        real_ip = _parse_ip(request.headers.get("x-real-ip"))
        if real_ip:
            return str(real_ip)
    return str(peer_ip) if peer_ip else peer
