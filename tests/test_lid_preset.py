"""One 2 in round-lid definition, recognised and explained in step 3 (user item 4)."""
import unittest

from lps import helptext, ladder, presets


class LidPreset(unittest.TestCase):
    def test_one_definition(self):
        t = presets.PIECES["tin50"]
        lad = ladder.lid_piece()
        self.assertEqual((t["w"], t["h"], t["shape"], t["origin"], tuple(t["margins"])),
                         (50.8, 50.8, "circle", "center", (2.54, 2.54, 2.54, 2.54)))
        same = lambda p: {k: v for k, v in p.items() if k != "name"}
        self.assertEqual(same(t), same(lad))                          # the ladder uses the same geometry
        self.assertEqual(presets.piece_choice_label(lad), t["name"])   # so step 3 recognises a ladder lid as tin50

    def test_explains_and_states_precedence(self):
        t = presets.PIECES["tin50"]
        e = presets.piece_explanation(t)
        self.assertIn("Reflective tin lid 2 in", e)
        self.assertIn("45.72 mm usable face", e)
        self.assertIn("job zero at the centre", e)
        self.assertIn("overrides the template", e)
        loaded = presets.piece_explanation(t, loaded_job=True)
        self.assertIn("saved size and margins win over any template", loaded)
        odd = dict(t, w=52.0, h=52.0)                                 # an override: recognised as a measured size
        self.assertIn("Measured size", presets.piece_explanation(odd))
        self.assertEqual(presets.piece_choice_label(odd), "Measured circle 52 x 52 mm")
        self.assertIn("margins are ignored", presets.piece_explanation(t, fit="exact"))

    def test_other_lid_sizes_still_work(self):
        p = ladder.lid_piece(76.2, 49.0)
        self.assertEqual((p["w"], p["margins"][0], p["origin"]), (76.2, 13.6, "center"))

    def test_guide_topics(self):
        names = [n for n, _ in helptext.topics(presets.BUILTIN[0])]
        for n in ("Round tins & jig centring", "Wood grain & finishing", "Machine changes & revalidation"):
            self.assertIn(n, names)


if __name__ == "__main__":
    unittest.main()
