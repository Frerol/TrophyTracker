import unittest

from retrocheevos.library import console_catalog


class GetCandidateConsoleIdsTests(unittest.TestCase):
    def test_unambiguous_extension_returns_single_console(self) -> None:
        self.assertEqual(console_catalog.get_candidate_console_ids("gba"), (5,))

    def test_is_case_insensitive(self) -> None:
        self.assertEqual(
            console_catalog.get_candidate_console_ids("GBA"),
            console_catalog.get_candidate_console_ids("gba"),
        )

    def test_ambiguous_extension_returns_multiple_candidates(self) -> None:
        candidates = console_catalog.get_candidate_console_ids("iso")
        self.assertIn(console_catalog.PSP, candidates)
        self.assertGreater(len(candidates), 1)

    def test_unknown_extension_returns_empty(self) -> None:
        self.assertEqual(console_catalog.get_candidate_console_ids("xyz"), ())

    def test_no_extension_is_both_single_and_ambiguous(self) -> None:
        overlap = set(console_catalog.SINGLE_CONSOLE_EXTENSIONS) & set(
            console_catalog.AMBIGUOUS_EXTENSION_CANDIDATES
        )
        self.assertEqual(overlap, set())


if __name__ == "__main__":
    unittest.main()
