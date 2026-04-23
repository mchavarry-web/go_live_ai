"""Unit tests for web search / URL extraction helpers."""

from app.tools.web_search import _format_extract_results, normalize_http_urls


class TestNormalizeHttpUrls:
    def test_extracts_multiple_from_one_string(self) -> None:
        s = "Mirá https://a.com/x y también https://b.com/y fin"
        out = normalize_http_urls([s], max_urls=10)
        assert out == ["https://a.com/x", "https://b.com/y"]

    def test_dedupes_and_respects_max(self) -> None:
        out = normalize_http_urls(
            ["https://x.com", "https://x.com", "https://y.com"],
            max_urls=2,
        )
        assert out == ["https://x.com", "https://y.com"]

    def test_strips_trailing_punctuation(self) -> None:
        out = normalize_http_urls(["https://example.com/path)."], max_urls=5)
        assert out == ["https://example.com/path"]

    def test_www_prefix(self) -> None:
        out = normalize_http_urls(["www.infobae.com/nota"], max_urls=5)
        assert out == ["https://www.infobae.com/nota"]

    def test_empty_when_no_url(self) -> None:
        assert normalize_http_urls(["sin enlace acá"], max_urls=5) == []


class TestFormatExtractResults:
    def test_string_passthrough(self) -> None:
        assert _format_extract_results("solo texto") == "solo texto"

    def test_formats_dict_with_results(self) -> None:
        payload = {
            "results": [
                {
                    "url": "https://u.test",
                    "title": "T",
                    "raw_content": "Hola mundo",
                }
            ],
            "failed_results": [],
        }
        text = _format_extract_results(payload)
        assert "https://u.test" in text
        assert "Hola mundo" in text
        assert "T" in text

    def test_failed_results_line(self) -> None:
        payload = {
            "results": [],
            "failed_results": [{"url": "https://bad", "error": "timeout"}],
        }
        text = _format_extract_results(payload)
        assert "https://bad" in text
        assert "timeout" in text
