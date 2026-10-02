"""English, Russian, Spanish, Portuguese and Ukrainian are five equal languages, not English-plus-one. These
tests hold that equality in place: the same keys everywhere, and real output in every one of the five -
so the next language is checked the same way a typo in English would be.

No network, no writing outside a temporary folder.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
LANG_DIR = os.path.join(ROOT, "lang")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import brief  # noqa: E402
import guard  # noqa: E402
import inbox  # noqa: E402
import tracker  # noqa: E402


def key_set(value, prefix=""):
    """Every key path in a nested dict, as dotted strings - "guard.family_words.mail" and so on."""
    found = set()
    if isinstance(value, dict):
        for key, sub in value.items():
            path = "%s.%s" % (prefix, key) if prefix else str(key)
            found.add(path)
            found |= key_set(sub, path)
    return found


class AllFiveLanguagesAgree(unittest.TestCase):
    def test_every_lang_file_has_the_same_keys_as_english(self):
        english = json.load(open(os.path.join(LANG_DIR, "en.json"), encoding="utf-8"))
        english_keys = key_set(english)
        for code in tracker.LANGS:
            if code == "en":
                continue
            with self.subTest(lang=code):
                table = json.load(open(os.path.join(LANG_DIR, "%s.json" % code), encoding="utf-8"))
                self.assertEqual(key_set(table), english_keys)

    def test_the_five_languages_are_equal_not_english_plus_one(self):
        self.assertEqual(tuple(tracker.LANGS), ("en", "ru", "es", "pt", "uk"))
        self.assertEqual(brief.LANGS, tracker.LANGS)
        self.assertEqual(inbox.LANGS, tracker.LANGS)


class TheBriefRendersInEveryLanguage(unittest.TestCase):
    def test_render_produces_real_text_in_all_five_languages(self):
        empty = {"ok": True, "now": "2026-01-01T00:00:00+00:00", "date": "2026-01-01", "night": False,
                 "done_24h": [], "waiting": [], "needs_you": [], "mine_today": [],
                 "counts": {"done_24h": 0, "waiting": 0, "needs_you": 0, "mine_today": 0}}
        for code in brief.LANGS:
            with self.subTest(lang=code):
                text = brief.render(empty, code)
                self.assertIn(brief.words_for(code)["empty_all"], text)
                self.assertTrue(text.strip())
                self.assertTrue(brief.file_name(code))


class TheInboxSpeaksEveryLanguage(unittest.TestCase):
    def test_every_language_has_its_own_words_and_done_dir(self):
        for code in inbox.LANGS:
            with self.subTest(lang=code):
                said = inbox.words(code)
                self.assertTrue(said["no_folder_yet"])
                self.assertIn(said["kinds"]["photo"], said["kinds"].values())
        self.assertEqual(len(set(inbox.DONE_DIRS)), len(inbox.LANGS))
        self.assertEqual(inbox.DONE_DIRS[0], "done")


class TheGuardRecognisesAYesInEveryLanguage(unittest.TestCase):
    """One real yes-phrase per family, per language - built from that language's own stem in
    lang/<code>.json, so a stem that only matches a form nobody types would show up here as a failure."""

    def test_one_yes_phrase_per_family_is_recognised_in_every_language(self):
        for code in tracker.LANGS:
            words = tracker.load_lang(code)["guard"]
            for family in ("mail", "money", "delete", "cancel"):
                stem = words["family_words"][family][0].lstrip("^")
                with self.subTest(lang=code, family=family):
                    said = "yes, %s please" % stem
                    self.assertTrue(guard.approval_covers(said, family, []), (code, family, said))

    def test_one_edit_phrase_is_recognised_in_every_language(self):
        for code in tracker.LANGS:
            stem = tracker.load_lang(code)["guard"]["edit_words"][0].lstrip("^")
            with self.subTest(lang=code):
                said = "yes, %s please" % stem
                self.assertTrue(guard.approval_covers(said, "overwrite", []), (code, said))

    def test_real_yes_phrases_in_spanish_and_portuguese(self):
        cases = [("s\u00ed, pague la factura de la tienda", "money"), ("sim, pague a fatura", "money"),
                 ("s\u00ed, env\u00eda la carta a la tienda", "mail"), ("sim, envie o e-mail", "mail"),
                 ("s\u00ed, borra el archivo", "delete"), ("sim, apague o arquivo", "delete"),
                 ("sim, altere a lista", "overwrite"), ("s\u00ed, guarde la lista", "overwrite")]
        for said, family in cases:
            with self.subTest(said=said):
                self.assertTrue(guard.approval_covers(said, family, []))

    def test_one_languages_stem_does_not_open_the_gate_on_another_languages_word(self):
        """Every language's stems are checked on every yes; a Latin-script stem must not fire on an
        ordinary English or Portuguese word (`page`, `guard`, `apagar`, `alternative`, `environment`)."""
        cases = [("yes, go to page 2 please", "money"), ("yes, call the guard please", "overwrite"),
                 ("sim, apagar a luz", "money"), ("sim, essa alternativa \u00e9 melhor", "overwrite"),
                 ("yes, check the environment", "mail"), ("yes, exclude the tests", "delete")]
        for said, family in cases:
            with self.subTest(said=said):
                self.assertFalse(guard.approval_covers(said, family, []))


if __name__ == "__main__":
    unittest.main()
