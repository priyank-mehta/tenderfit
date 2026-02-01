import unittest

from tenderfit.tools.bidplus_scout import _normalize_bid, _score_bid


class BidPlusScoutTests(unittest.TestCase):
    def test_normalize_bid(self) -> None:
        doc = {
            "b_id": [123456],
            "b_bid_number": ["GEM/2025/B/1234567"],
            "bd_category_name": ["Vehicle Hiring Service"],
            "final_end_date_sort": ["2026-02-02T09:00:00Z"],
            "b_bid_type": [1],
            "b_eval_type": [0],
            "ba_official_details_minName": ["Ministry of Transport"],
            "ba_official_details_deptName": ["Fleet Dept"],
        }
        bid = _normalize_bid(doc)
        self.assertEqual(bid["bid_id"], "GEM/2025/B/1234567")
        self.assertEqual(bid["title"], "Vehicle Hiring Service")
        self.assertEqual(
            bid["url"],
            "https://bidplus.gem.gov.in/showbidDocument/123456",
        )
        self.assertEqual(bid["closing_date"], "2026-02-02T09:00:00Z")
        self.assertEqual(bid["summary"], "Ministry of Transport | Fleet Dept")

    def test_score_bid(self) -> None:
        bid = {
            "title": "Taxi Hiring Service",
            "summary": "Ministry of Transport",
            "bid_id": "GEM/2025/B/1234567",
            "ministry": "Ministry of Transport",
            "department": "Fleet Dept",
        }
        tokens = ["taxi", "fleet"]
        score = _score_bid(bid, tokens)
        self.assertEqual(score, 2.0)


if __name__ == "__main__":
    unittest.main()
