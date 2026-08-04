import ipaddress

from fastapi import Request


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


def client_ip(request: Request) -> str:
    peer = request.client.host if request.client and request.client.host else "unknown"
    peer_ip = _parse_ip(peer)
    peer_is_trusted_proxy = bool(peer_ip and (peer_ip.is_loopback or peer_ip.is_private))
    if peer_is_trusted_proxy:
        for header_name in TRUSTED_CLIENT_IP_HEADERS:
            header_ip = _parse_ip(request.headers.get(header_name))
            if header_ip:
                return str(header_ip)
        forwarded = request.headers.get("x-forwarded-for", "")
        for raw_part in reversed(forwarded.split(",")):
            forwarded_ip = _parse_ip(raw_part)
            if forwarded_ip:
                return str(forwarded_ip)
        real_ip = _parse_ip(request.headers.get("x-real-ip"))
        if real_ip:
            return str(real_ip)
    return str(peer_ip) if peer_ip else peer
