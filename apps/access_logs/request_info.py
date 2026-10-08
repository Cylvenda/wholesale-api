"""Read an HTTP request's origin: address, device, and place.

Kept dependency-light on purpose. Device details come from a small parser for
the user-agent string, and location comes from a local MaxMind database when one
has been configured. Without a database the log still records the exact address,
device and browser, and the geographic fields simply stay blank.
"""

import ipaddress
import re

from django.conf import settings

# Ordered most specific first: Edge and Opera both claim to be Chrome.
_BROWSERS = (
    ("Edge", r"Edg(?:e|A|iOS)?/"),
    ("Opera", r"OPR/|Opera"),
    ("Samsung Internet", r"SamsungBrowser/"),
    ("Chrome", r"(?:Chrome|CriOS)/"),
    ("Firefox", r"(?:Firefox|FxiOS)/"),
    ("Safari", r"Version/.*Safari/"),
    ("Internet Explorer", r"MSIE |Trident/"),
)

_OPERATING_SYSTEMS = (
    ("Windows", r"Windows"),
    ("iOS", r"iPhone|iPad|iPod"),
    ("Android", r"Android"),
    ("macOS", r"Mac OS X|Macintosh"),
    ("ChromeOS", r"CrOS"),
    ("Linux", r"Linux|X11"),
)

_DEVICE_TYPES = (
    ("tablet", r"iPad|Tablet|PlayBook|Silk|Android(?!.*Mobile)"),
    ("mobile", r"Mobile|iPhone|iPod|Android|Windows Phone|BlackBerry|Opera Mini"),
    ("desktop", r"Windows|Macintosh|X11|CrOS|Linux"),
)


def get_client_ip(request):
    """The address to attribute the request to.

    Only trusted proxy headers are honoured when the peer is a proxy Django
    itself trusts, so a client cannot fake its address by sending a header.
    """
    remote = request.META.get("REMOTE_ADDR", "").strip()
    if remote in ("", "127.0.0.1", "::1") or _is_trusted_proxy(remote):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        candidates = [part.strip() for part in forwarded.split(",") if part.strip()]
        for candidate in candidates:
            if _is_valid_ip(candidate):
                return candidate
    return remote if _is_valid_ip(remote) else "0.0.0.0"


def _is_valid_ip(value):
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _is_trusted_proxy(remote):
    trusted = getattr(settings, "ACCESS_LOG_TRUSTED_PROXIES", None) or []
    if not trusted:
        return False
    try:
        address = ipaddress.ip_address(remote)
    except ValueError:
        return False
    for entry in trusted:
        try:
            if address in ipaddress.ip_network(str(entry), strict=False):
                return True
        except ValueError:
            continue
    return False


def _match(agent, table):
    for label, pattern in table:
        if re.search(pattern, agent, re.IGNORECASE):
            return label
    return ""


def describe_device(user_agent):
    """Split a user-agent string into a device type, OS and browser."""
    agent = (user_agent or "").strip()
    if not agent:
        return "", "", ""
    return (
        _match(agent, _DEVICE_TYPES),
        _match(agent, _OPERATING_SYSTEMS),
        _match(agent, _BROWSERS),
    )


class GeoResolver:
    """Look an address up in a local MaxMind database, when one exists.

    The database is loaded once and cached; if `geoip2` is not installed or
    `ACCESS_LOG_GEOIP_DATABASE` does not point at a readable file, every lookup
    returns nothing rather than raising.
    """

    def __init__(self):
        self._reader = None
        self._loaded = False

    def _load(self):
        if self._loaded:
            return self._reader
        self._loaded = True
        path = getattr(settings, "ACCESS_LOG_GEOIP_DATABASE", "") or ""
        if not path:
            return None
        try:
            import geoip2.database  # noqa: PLC0415 - optional dependency
        except ImportError:
            return None
        try:
            self._reader = geoip2.database.Reader(path)
        except (OSError, ValueError):
            self._reader = None
        return self._reader

    def lookup(self, ip_address):
        """Return {country, country_code, region, city, latitude, longitude}."""
        reader = self._load()
        if reader is None:
            return {}
        try:
            response = reader.city(str(ip_address))
        except Exception:  # noqa: BLE001 - unknown address, not a failure
            return {}
        subdivision = response.subdivisions.most_specific
        return {
            "country": response.country.name or "",
            "country_code": response.country.iso_code or "",
            "region": subdivision.name if subdivision else "",
            "city": response.city.name or "",
            "latitude": response.location.latitude,
            "longitude": response.location.longitude,
        }


resolver = GeoResolver()


def describe_location(ip_address):
    """Best-effort geography for an address; always safe to call."""
    if _is_private_address(ip_address):
        return {}
    return resolver.lookup(ip_address)


def _is_private_address(ip_address):
    try:
        address = ipaddress.ip_address(ip_address)
    except ValueError:
        return True
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )