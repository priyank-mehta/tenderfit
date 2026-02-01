import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tenderfit.tools.chunk_text import chunk_text
from tenderfit.tools.fetch_docs import fetch_docs
from tenderfit.tools.parse_pdf import parse_pdf
from tenderfit.tools.search_bids import search_bids
from tenderfit.tools.validate_schema import validate_schema

try:
    from pypdf import PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import jsonschema  # noqa: F401
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False


class ToolRuntimeTests(unittest.TestCase):
    def test_search_bids_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            data_file = tmp_path / "bids.json"
            now = datetime.now(timezone.utc).isoformat()
            data_file.write_text(
                json.dumps(
                    [
                        {
                            "bid_id": "BID-001",
                            "title": "Taxi hiring for campus",
                            "published_at": now,
                            "url": "https://example.com/bid-1",
                        },
                        {
                            "bid_id": "BID-002",
                            "title": "Office supplies",
                            "published_at": now,
                            "url": "https://example.com/bid-2",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            output = search_bids(
                keyword="taxi",
                days=7,
                top_n=10,
                data_path=str(data_file),
                cache_dir=str(tmp_path / "cache"),
            )
            self.assertFalse(output.cached)
            self.assertEqual(len(output.bids), 1)

            cached_output = search_bids(
                keyword="taxi",
                days=7,
                top_n=10,
                data_path=str(data_file),
                cache_dir=str(tmp_path / "cache"),
            )
            self.assertTrue(cached_output.cached)
            self.assertEqual(len(cached_output.bids), 1)

    def test_fetch_docs_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_file = tmp_path / "doc1.pdf"
            source_file.write_text("example", encoding="utf-8")

            out_dir = tmp_path / "out"
            cache_dir = tmp_path / "cache"
            url = f"file://{source_file}"

            output = fetch_docs(
                bid_id="BID-001",
                doc_urls=[url],
                out_dir=str(out_dir),
                cache_dir=str(cache_dir),
            )
            self.assertFalse(output.cached)
            self.assertEqual(len(output.downloaded), 1)
            self.assertTrue(Path(output.downloaded[0]).exists())

            cached_output = fetch_docs(
                bid_id="BID-001",
                doc_urls=[url],
                out_dir=str(out_dir),
                cache_dir=str(cache_dir),
            )
            self.assertTrue(cached_output.cached)

    def test_chunk_text_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            pages = [
                {"page_num": 1, "text": "A" * 1200},
                {"page_num": 2, "text": "B" * 200},
            ]
            output = chunk_text(
                pages=pages,
                chunk_size=500,
                overlap=50,
                cache_dir=str(cache_dir),
            )
            self.assertFalse(output.cached)
            self.assertGreater(len(output.chunks), 1)

            cached_output = chunk_text(
                pages=pages,
                chunk_size=500,
                overlap=50,
                cache_dir=str(cache_dir),
            )
            self.assertTrue(cached_output.cached)

    @unittest.skipUnless(HAS_PYPDF, "pypdf not installed")
    def test_parse_pdf_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            pdf_path = tmp_path / "sample.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            with pdf_path.open("wb") as handle:
                writer.write(handle)

            cache_dir = tmp_path / "cache"
            output = parse_pdf(pdf_path=str(pdf_path), cache_dir=str(cache_dir))
            self.assertFalse(output.cached)
            self.assertEqual(len(output.pages), 1)

            cached_output = parse_pdf(pdf_path=str(pdf_path), cache_dir=str(cache_dir))
            self.assertTrue(cached_output.cached)

    @unittest.skipUnless(HAS_JSONSCHEMA, "jsonschema not installed")
    def test_validate_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            schema_path = tmp_path / "schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                        "additionalProperties": False,
                    }
                ),
                encoding="utf-8",
            )
            cache_dir = tmp_path / "cache"

            output = validate_schema(
                schema_path=str(schema_path),
                data={"name": "ACME"},
                cache_dir=str(cache_dir),
            )
            self.assertTrue(output.valid)
            self.assertFalse(output.cached)

            invalid = validate_schema(
                schema_path=str(schema_path),
                data={"missing": True},
                cache_dir=str(cache_dir),
            )
            self.assertFalse(invalid.valid)
            self.assertGreater(len(invalid.errors), 0)


if __name__ == "__main__":
    unittest.main()
