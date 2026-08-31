"""SSRF korumalı, HTTPS'e yükselten ve TLS zincirini doğrulayan erişim."""
from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

INTERMEDIATE = (
    Path(__file__).parent / "certificates" /
    "globalsign-rsa-ov-ssl-ca-2018.pem"
)
INTERMEDIATE_SHA256 = (
    "b676ffa3179e8812093a1b5eafee876ae7a6aaf231078dad1bfb21cd2893764a"
)
ALLOWED_TYPES = frozenset(
    {"application/pdf", "text/html", "application/xhtml+xml",
     "image/png", "image/jpeg", "image/tiff"}
)
REDIRECTS = frozenset({301, 302, 303, 307, 308})
OFFICIAL_DOMAIN_SUFFIXES = frozenset(
    {"gov.tr", "bel.tr", "pol.tr", "tsk.tr", "edu.tr", "k12.tr"}
)


class SecurityError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message

    def to_dict(self) -> dict[str, str]:
        return {"status": "blocked", "code": self.code, "message": self.message}


def _host(value: str) -> str:
    try:
        return value.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise SecurityError("invalid_hostname", "Geçersiz alan adı.") from exc


@dataclass(frozen=True)
class Policy:
    allowed_hosts: frozenset[str] = frozenset()
    official_suffixes: frozenset[str] = OFFICIAL_DOMAIN_SUFFIXES
    max_redirects: int = 3
    timeout: float = 15
    max_bytes: int = 20 * 1024 * 1024
    allowed_types: frozenset[str] = ALLOWED_TYPES

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "allowed_hosts", frozenset(_host(h) for h in self.allowed_hosts)
        )
        object.__setattr__(
            self,
            "official_suffixes",
            frozenset(_host(s) for s in self.official_suffixes),
        )
        if not self.allowed_hosts and not self.official_suffixes:
            raise ValueError("Alan adı doğrulama kuralı gerekir.")

    def allows(self, hostname: str) -> bool:
        hostname = _host(hostname)
        if self.allowed_hosts:
            return hostname in self.allowed_hosts
        return any(
            hostname.endswith(f".{suffix}")
            for suffix in self.official_suffixes
        )

    def validation_mode(self) -> str:
        return "explicit_allowlist" if self.allowed_hosts else "official_domain"

    def pin(self, hostname: str) -> Policy:
        """İlk doğrulanan alan adından sonra hedefi aynı tam hosta sabitler."""
        return replace(self, allowed_hosts=frozenset({_host(hostname)}))


@dataclass(frozen=True)
class Target:
    original_url: str
    url: str
    hostname: str
    path_query: str
    upgraded: bool
    port: int = 443


@dataclass(frozen=True)
class FetchResult:
    original_url: str
    final_url: str
    transport_upgraded: bool
    status_code: int
    content_type: str
    content_length: int
    sha256: str
    connected_ip: str
    redirects: list[str]
    body: bytes = field(repr=False)

    def metadata(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("body")
        return data


def prepare(url: str, policy: Policy) -> Target:
    if not url or len(url) > 4096:
        raise SecurityError("invalid_url", "URL boş veya çok uzun.")
    if "\\" in url or any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise SecurityError("invalid_url", "URL güvenli olmayan karakter içeriyor.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise SecurityError("invalid_url", "URL ayrıştırılamadı.") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise SecurityError("scheme_not_allowed", "Yalnızca HTTP/HTTPS kabul edilir.")
    if not parsed.hostname:
        raise SecurityError("missing_hostname", "Alan adı eksik.")
    if parsed.username is not None or parsed.password is not None:
        raise SecurityError("userinfo_not_allowed", "URL kullanıcı bilgisi içeremez.")
    if parsed.fragment:
        raise SecurityError("fragment_not_allowed", "URL fragment içeremez.")
    hostname = _host(parsed.hostname)
    if not policy.allows(hostname):
        raise SecurityError(
            "host_not_allowed",
            f"Resmî kurum alan adı olarak doğrulanamadı: {hostname}",
        )
    expected_port = 80 if scheme == "http" else 443
    if port not in (None, expected_port):
        raise SecurityError("port_not_allowed", "Özel porta izin verilmez.")
    path = parsed.path or "/"
    return Target(
        original_url=url,
        url=urlunsplit(("https", hostname, path, parsed.query, "")),
        hostname=hostname,
        path_query=urlunsplit(("", "", path, parsed.query, "")),
        upgraded=scheme == "http",
    )


def resolve_public(target: Target) -> list[str]:
    try:
        records = socket.getaddrinfo(
            target.hostname, 443, type=socket.SOCK_STREAM
        )
    except socket.gaierror as exc:
        raise SecurityError("dns_failed", "Alan adı çözümlenemedi.") from exc
    addresses: list[str] = []
    for record in records:
        address = ipaddress.ip_address(record[4][0].split("%", 1)[0])
        public = address.ipv4_mapped.is_global if (
            isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped
        ) else address.is_global
        if not public:
            raise SecurityError(
                "non_public_address", f"Genel olmayan IP engellendi: {address}"
            )
        addresses.append(address.compressed)
    return list(dict.fromkeys(addresses))


def _tls_context() -> ssl.SSLContext:
    if not INTERMEDIATE.is_file():
        raise SecurityError("missing_ca", "GlobalSign ara sertifikası bulunamadı.")
    der = ssl.PEM_cert_to_DER_cert(INTERMEDIATE.read_text(encoding="ascii"))
    if hashlib.sha256(der).hexdigest() != INTERMEDIATE_SHA256:
        raise SecurityError("ca_mismatch", "Ara sertifika parmak izi eşleşmiyor.")
    defaults = ssl.get_default_verify_paths()
    if defaults.cafile and Path(defaults.cafile).is_file():
        context = ssl.create_default_context()
    elif Path("/etc/ssl/cert.pem").is_file():
        context = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    else:
        context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(INTERMEDIATE))
    return context


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, target: Target, ip: str, timeout: float):
        self.ip = ip
        super().__init__(
            target.hostname, 443, timeout=timeout, context=_tls_context()
        )

    def connect(self) -> None:
        self.sock = self._create_connection(
            (self.ip, 443), self.timeout, self.source_address
        )
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def _request(target: Target, ip: str, policy: Policy):
    connection = _PinnedHTTPS(target, ip, policy.timeout)
    try:
        connection.request(
            "GET", target.path_query,
            headers={
                "Host": target.hostname,
                "User-Agent": "document-verifier/0.1",
                "Accept": "application/pdf,text/html,application/xhtml+xml",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        headers = {k.lower(): v.strip() for k, v in response.getheaders()}
        declared = headers.get("content-length")
        if declared and int(declared) > policy.max_bytes:
            raise SecurityError("too_large", "Yanıt boyut sınırını aşıyor.")
        body = response.read(policy.max_bytes + 1)
        if len(body) > policy.max_bytes:
            raise SecurityError("too_large", "Yanıt boyut sınırını aşıyor.")
        return response.status, headers, body
    finally:
        connection.close()


def safe_fetch(url: str, policy: Policy) -> FetchResult:
    original, current, upgraded, redirects = url, url, False, []
    for index in range(policy.max_redirects + 1):
        target = prepare(current, policy)
        upgraded = upgraded or target.upgraded
        status = headers = body = connected_ip = None
        last_error: Exception | None = None
        for ip in resolve_public(target):
            try:
                status, headers, body = _request(target, ip, policy)
                connected_ip = ip
                break
            except SecurityError:
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                last_error = exc
        if status is None:
            raise SecurityError("connection_failed", f"Bağlantı kurulamadı: {last_error}")
        if status in REDIRECTS:
            location = headers.get("location")
            if not location or index >= policy.max_redirects:
                raise SecurityError("redirect_blocked", "Yönlendirme engellendi.")
            redirects.append(target.url)
            current = urljoin(target.url, location)
            continue
        if status != 200:
            raise SecurityError("unexpected_status", f"Sunucu HTTP {status} döndürdü.")
        content_type = headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in policy.allowed_types:
            raise SecurityError(
                "content_type_blocked", f"İzin verilmeyen tür: {content_type}"
            )
        return FetchResult(
            original, target.url, upgraded, status, content_type, len(body),
            hashlib.sha256(body).hexdigest(), connected_ip, redirects, body
        )
    raise SecurityError("redirect_blocked", "Yönlendirme sınırı aşıldı.")
