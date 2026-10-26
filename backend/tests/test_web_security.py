import asyncio
import socket
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.research.errors import ResearchFailure
from app.research.web import (
    PublicResolver,
    SecureHTTP,
    extract_text,
    normalize_url,
    relevant_excerpt,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a",
        "http://224.0.0.1",
        "http://[ff02::1]",
        "http://255.255.255.255",
        "http://2130706433",
        "http://127.1",
        "http://0177.0.0.1",
        "http://0x7f000001",
        "http://0x7f.0.0.1",
        "http://10.0.0.1",
        "http://172.16.1.1",
        "http://192.168.1.1",
        "http://169.254.169.254/latest/meta-data",
        "http://0.0.0.0",
        "http://[::1]",
        "http://[fc00::1]",
        "http://[::ffff:127.0.0.1]",
        "file:///etc/passwd",
        "ftp://example.org",
        "https://user:password@example.org",
        "http://localhost",
        "http://anything.localhost",
        "http://server.local",
        "https://example.org:8443",
        "http://example.org/\nsecret",
        "https://example.org\\@127.0.0.1",
        "http://[fe80::1%25en0]",
    ],
)
def test_unsafe_url_forms_rejected(url: str) -> None:
    with pytest.raises(ResearchFailure):
        normalize_url(url)


def test_url_normalization_removes_only_tracking_and_fragment() -> None:
    assert normalize_url('https://example.org/a"<b>') == "https://example.org/a%22%3Cb%3E"
    assert (
        normalize_url("https://EXAMPLE.ORG:443/paper?b=2&utm_source=x&a=1#part")
        == "https://example.org/paper?a=1&b=2"
    )


def test_excerpt_prefers_query_overlap_over_unrelated_page_prefix() -> None:
    text = "Unrelated introduction. " * 120 + "Grounded evidence provenance links sources. " * 20
    excerpt = relevant_excerpt(text, "grounded evidence provenance")
    assert "Grounded evidence provenance" in excerpt
    assert len(excerpt) <= 1500


@pytest.mark.parametrize(
    "addresses", [["8.8.8.8", "127.0.0.1"], ["169.254.169.254"], ["::ffff:10.0.0.1"]]
)
def test_connection_resolver_rejects_mixed_private_and_rebound_answers(
    monkeypatch: pytest.MonkeyPatch, addresses: list[str]
) -> None:
    async def exercise() -> None:
        answers = [
            (
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_STREAM,
                6,
                "",
                (address, 443),
            )
            for address in addresses
        ]
        monkeypatch.setattr(
            asyncio.get_running_loop(), "getaddrinfo", AsyncMock(return_value=answers)
        )
        with pytest.raises(ResearchFailure):
            await PublicResolver().resolve("rebound.example.org", 443)

    asyncio.run(exercise())


def test_resolver_returns_validated_addresses_for_actual_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        monkeypatch.setattr(
            asyncio.get_running_loop(),
            "getaddrinfo",
            AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]),
        )
        answers = await PublicResolver().resolve("public.example.org", 443)
        assert answers[0]["host"] == "8.8.8.8"
        assert answers[0]["hostname"] == "public.example.org"

    asyncio.run(exercise())


def fake_client(
    monkeypatch: pytest.MonkeyPatch, statuses: list[tuple[int, dict[str, str], bytes]]
) -> MagicMock:
    contexts = []
    for status, headers, body in statuses:

        async def chunks(size: int, data: bytes = body) -> AsyncIterator[bytes]:
            yield data

        response = SimpleNamespace(
            status=status,
            headers=headers,
            content_length=None,
            content=SimpleNamespace(iter_chunked=chunks),
        )
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        contexts.append(context)
    client = MagicMock()
    client.get.side_effect = contexts
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("app.research.web.aiohttp.ClientSession", MagicMock(return_value=client))
    monkeypatch.setattr("app.research.web.aiohttp.TCPConnector", MagicMock())
    return client


def test_redirect_to_private_target_is_never_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fake_client(monkeypatch, [(302, {"Location": "http://127.0.0.1/private"}, b"")])
    with pytest.raises(ResearchFailure):
        asyncio.run(SecureHTTP().get("https://example.org"))
    assert client.get.call_count == 1
    assert client.get.call_args.kwargs["allow_redirects"] is False


def test_api_key_is_never_forwarded_through_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fake_client(monkeypatch, [(302, {"Location": "https://other.example.org/"}, b"")])
    with pytest.raises(ResearchFailure):
        asyncio.run(
            SecureHTTP().get("https://example.org", {"X-Subscription-Token": "fake"}, redirects=0)
        )
    assert client.get.call_count == 1


def test_redirect_reserves_next_attempt_before_following_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        client = fake_client(
            monkeypatch,
            [
                (302, {"Location": "https://other.example.org/page"}, b""),
                (200, {"Content-Type": "text/plain"}, b"safe fixture passage"),
            ],
        )
        reservations = 0

        async def reserve() -> None:
            nonlocal reservations
            reservations += 1
            raise ResearchFailure("request_budget_exceeded")

        with pytest.raises(ResearchFailure, match="request_budget_exceeded"):
            await SecureHTTP(reserve_redirect=reserve).get("https://example.org/page")
        assert reservations == 1
        assert client.get.call_count == 1

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "headers,body",
    [
        ({"Content-Type": "text/html"}, b"x" * 2048),
        ({"Content-Type": "text/html", "Content-Encoding": "gzip"}, b"compressed"),
        ({"Content-Type": "application/pdf"}, b"pdf"),
    ],
)
def test_download_and_encoding_limits(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], body: bytes
) -> None:
    fake_client(monkeypatch, [(200, headers, body)])
    with pytest.raises(ResearchFailure):
        asyncio.run(SecureHTTP(max_bytes=1024).get("https://example.org/"))


def test_extractor_discards_scripts_styles_and_navigation() -> None:
    text = extract_text(
        b"<nav>menu</nav><script>steal()</script><style>hidden</style>"
        b"<main>Actual evidence &amp; methods.</main>",
        "text/html",
    )
    assert text == "Actual evidence & methods."
