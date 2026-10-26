import asyncio
import hashlib
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult

from app.research.errors import ResearchFailure, TransientProviderError


def normalize_url(value: str) -> str:
    try:
        if len(value) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in value) or "\\" in value:
            raise ValueError
        parsed = urlsplit(value)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or "%" in parsed.netloc
            or parsed.port not in {None, 443 if parsed.scheme == "https" else 80}
        ):
            raise ValueError
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        # aiohttp treats legacy numeric IPv4 spellings as literals and can skip its
        # resolver. Accept only canonical literals that ipaddress has validated.
        if address is None and re.fullmatch(r"[0-9.]+", host):
            raise ValueError
        if address is None:
            try:
                socket.inet_aton(host)
            except OSError:
                pass
            else:
                raise ValueError  # Legacy hexadecimal/octal IPv4 spellings are not accepted.
        if address is not None and not public_address(str(address)):
            raise ValueError
        netloc = f"[{host}]" if ":" in host else host
        query = urlencode(
            sorted(
                (k, v)
                for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid"}
            )
        )
        path = quote(parsed.path or "/", safe="/:@-._~!$&'()*+,;=%")
        return urlunsplit((parsed.scheme, netloc, path, query, ""))
    except (ValueError, UnicodeError) as exc:
        raise ResearchFailure("unsafe_url") from exc


def public_address(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return public_address(str(address.ipv4_mapped))
        if address.sixtofour or address.teredo:
            return False
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
        and not address.is_loopback
        and not address.is_link_local
    )


class PublicResolver(AbstractResolver):
    """Validate every DNS answer used by the actual connection, not a preflight lookup."""

    async def resolve(
        self, host: str, port: int = 0, family: int = socket.AF_INET
    ) -> list[ResolveResult]:
        answers = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
            family=family,
        )
        if not answers or any(not public_address(answer[4][0]) for answer in answers):
            raise ResearchFailure("unsafe_url")
        return [
            ResolveResult(
                hostname=host,
                host=answer[4][0],
                port=port,
                family=answer[0],
                proto=answer[2],
                flags=socket.AI_NUMERICHOST,
            )
            for answer in answers
        ]

    async def close(self) -> None:
        pass


class SecureHTTP:
    def __init__(
        self,
        max_bytes: int = 512000,
        timeout: float = 15,
        reserve_redirect: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.reserve_redirect = reserve_redirect

    async def get(
        self, url: str, headers: dict[str, str] | None = None, redirects: int = 3
    ) -> tuple[str, bytes, str]:
        current = normalize_url(url)
        connector = aiohttp.TCPConnector(
            resolver=PublicResolver(), use_dns_cache=False, force_close=True, limit=2
        )
        async with aiohttp.ClientSession(
            connector=connector,
            trust_env=False,
            cookie_jar=aiohttp.DummyCookieJar(),
            auto_decompress=False,
            timeout=aiohttp.ClientTimeout(total=self.timeout, connect=3),
        ) as client:
            for step in range(redirects + 1):
                try:
                    async with client.get(
                        current,
                        allow_redirects=False,
                        headers={
                            "User-Agent": "ResearchForge/0.1 (local research)",
                            "Accept-Encoding": "identity",
                            **(headers or {}),
                        },
                    ) as response:
                        if response.status in {301, 302, 303, 307, 308}:
                            if step == redirects or headers:
                                raise ResearchFailure("redirect_rejected")
                            target = normalize_url(
                                urljoin(current, response.headers.get("Location", ""))
                            )
                            if current.startswith("https:") and not target.startswith("https:"):
                                raise ResearchFailure("redirect_rejected")
                            if self.reserve_redirect is not None:
                                await self.reserve_redirect()
                            current = target
                            continue
                        if response.status == 429 or response.status >= 500:
                            raise TransientProviderError("http_transient")
                        if response.status != 200:
                            raise ResearchFailure("http_unavailable")
                        if (
                            response.headers.get("Content-Encoding", "identity").lower()
                            != "identity"
                        ):
                            raise ResearchFailure("unsupported_encoding")
                        if (
                            response.content_length is not None
                            and response.content_length > self.max_bytes
                        ):
                            raise ResearchFailure("page_too_large")
                        content_type = (
                            response.headers.get("Content-Type", "").split(";")[0].lower()
                        )
                        if content_type not in {
                            "text/html",
                            "text/plain",
                            "application/json",
                            "application/xhtml+xml",
                        }:
                            raise ResearchFailure("unsupported_content")
                        body = bytearray()
                        async for chunk in response.content.iter_chunked(8192):
                            body.extend(chunk)
                            if len(body) > self.max_bytes:
                                raise ResearchFailure("page_too_large")
                        return current, bytes(body), content_type
                except aiohttp.ClientError as exc:
                    raise TransientProviderError("http_connection") from exc
        raise ResearchFailure("redirect_rejected")


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "header", "footer", "form", "noscript", "template"}:
            self.ignored.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.ignored and tag == self.ignored[-1]:
            self.ignored.pop()

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def extract_text(body: bytes, content_type: str) -> str:
    decoded = body.decode("utf-8", errors="replace")
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = PageText()
        parser.feed(decoded)
        decoded = " ".join(parser.parts)
    elif content_type != "text/plain":
        raise ResearchFailure("unsupported_content")
    return " ".join(decoded.replace("\x00", "").split())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def relevant_excerpt(text: str, query: str) -> str:
    """Small lexical baseline; selection is not a relevance or truth guarantee."""
    terms = set(re.findall(r"\w{3,}", query.casefold())) - {
        "the",
        "and",
        "for",
        "with",
        "how",
        "does",
        "what",
        "are",
    }
    windows = [
        text[start : start + 1500] for start in range(0, len(text), 1000) if len(text) - start >= 40
    ]
    return max(
        windows,
        key=lambda passage: len(terms & set(re.findall(r"\w{3,}", passage.casefold()))),
        default=text[:1500],
    )
