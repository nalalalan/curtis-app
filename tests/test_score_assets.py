import unittest

from backend.app.score_assets import ensure_score_pdf, score_asset_source_state


class ScoreAssetTests(unittest.TestCase):
    def test_wieniawski_uses_vendored_imslp_pdf_before_network(self):
        state = score_asset_source_state("wieniawski-scherzo-tarantelle-vln")

        self.assertEqual(state["status"], "local_source_pdf_ready")
        self.assertTrue(state["sourcePdfLocalReady"])
        self.assertEqual(state["sourcePdfLocalPath"], "assets/score/wieniawski-scherzo-tarantelle-solo-imslp.pdf")
        self.assertTrue(str(ensure_score_pdf("wieniawski-scherzo-tarantelle-vln")).endswith("wieniawski-scherzo-tarantelle-solo-imslp.pdf"))


if __name__ == "__main__":
    unittest.main()
