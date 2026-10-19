"""Politique commune des URL et résolution vers des adresses publiques."""

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURLError(ValueError):
    """URL interdite pour la collecte documentaire."""


def validate_url(url: str, allowed_domains: list[str] | None = None) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError("URL HTTP(S) avec domaine requise")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURLError("Identifiants interdits dans l'URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURLError("Port invalide") from exc
    if port not in {None, 80, 443}:
        raise UnsafeURLError("Port non autorisé")
    hostname = parsed.hostname.lower().rstrip(".")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise UnsafeURLError("Adresse IP directe interdite")
    if "." not in hostname or hostname.endswith((".localhost", ".local", ".internal", ".test")):
        raise UnsafeURLError("Domaine local ou réservé interdit")
    if allowed_domains and hostname not in {d.lower().rstrip('.') for d in allowed_domains}:
        raise UnsafeURLError("Domaine absent de la liste autorisée")


def resolve_public_address(url: str) -> str:
    """Vérifie toutes les réponses DNS ; l'appelant doit utiliser l'IP retournée."""
    validate_url(url)
    parsed = urlsplit(url)
    addresses = socket.getaddrinfo(
        parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
        type=socket.SOCK_STREAM,
    )
    ips = [str(item[4][0]) for item in addresses]
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise UnsafeURLError("Résolution DNS vers une adresse non publique")
    return ips[0]
