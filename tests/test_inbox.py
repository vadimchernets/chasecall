"""The folder is the only place where Chasecall looks at something the person owns, so the promises about it have
to hold literally: what is shown is shown once, nothing is read, nothing is deleted, nothing is overwritten, only
the one folder they named is ever touched, and a folder that is not there today is not a crash.

A name in that folder came from a phone, or from a cloud folder somebody else can write into. It is a name and
never a command: the moving is done by this script, so no name is ever handed to a shell.

No network, no writing outside a temporary folder.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
import inbox  # noqa: E402
import tracker  # noqa: E402

NOW = "2026-09-24T14:00:00+00:00"
# A name a phone can really produce, and a shell would really obey. It is the whole reason the move happens in
# Python: `mv "<folder>/note" ; echo PWNED ; "x.txt"` runs the middle of the file name.
NASTY = 'note" ; echo PWNED ; "x.txt'


class Base(unittest.TestCase):
    KEYS = ("CHASECALL_DB", "CHASECALL_NOW", "CHASECALL_LANG")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = {key: os.environ.get(key) for key in self.KEYS}
        for key in self.KEYS:
            os.environ.pop(key, None)
        # what we remember is the real path, so the tests compare against the real path too
        self.root = os.path.realpath(self.tmp.name)
        self.db = os.path.join(self.root, "chasecall.db")
        os.environ["CHASECALL_DB"] = self.db
        os.environ["CHASECALL_NOW"] = NOW
        self.folder = os.path.join(self.root, "From the phone")
        os.makedirs(self.folder)
        self.conn = inbox.connect()

    def tearDown(self):
        self.conn.close()
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def drop(self, name, text="x", folder=None):
        path = os.path.join(folder or self.folder, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def names(self, result):
        return [entry["name"] for entry in result["files"]]

    def cli(self, *args, **kwargs):
        env = dict(os.environ)
        env.update(kwargs.get("env_extra") or {})
        done = subprocess.run([sys.executable, os.path.join(SCRIPTS, "inbox.py")] + list(args),
                              capture_output=True, text=True, env=env, timeout=60)
        try:
            data = json.loads(done.stdout)
        except ValueError:
            data = None
        return done.returncode, data, done.stdout, done.stderr


class WhatIsNew(Base):
    def setUp(self):
        super().setUp()
        self.drop("IMG_4821.HEIC", "a photograph of a letter")
        self.drop("roof.txt", "call the roofer")
        self.drop("Recording 7.m4a", "twenty seconds")

    def test_everything_in_the_folder_is_new_the_first_time(self):
        result = inbox.list_files(self.conn, self.folder)
        self.assertEqual(result["count"], 3)
        self.assertEqual(sorted(self.names(result)), ["IMG_4821.HEIC", "Recording 7.m4a", "roof.txt"])
        self.assertEqual(sorted(entry["kind"] for entry in result["files"]), ["note", "photo", "voice"])
        for entry in result["files"]:
            self.assertEqual(entry["state"], "new")
            self.assertTrue(entry["size"] > 0)
            self.assertTrue(entry["modified_at"].startswith("20"))

    def test_what_was_shown_once_is_not_shown_again(self):
        self.assertEqual(inbox.list_files(self.conn, self.folder)["count"], 3)
        again = inbox.list_files(self.conn, self.folder)
        self.assertEqual(again["count"], 0)
        self.assertEqual(again["counts"], {"new": 0, "pending": 3, "done": 0, "total": 3})
        self.assertIn("Nothing new from the phone", inbox.render_list(again))
        self.assertIn("3 more were shown earlier", inbox.render_list(again))

    def test_but_nothing_shown_is_lost_it_is_still_waiting_to_be_sorted(self):
        inbox.list_files(self.conn, self.folder)
        pending = inbox.list_files(self.conn, self.folder, scope="pending")
        self.assertEqual(sorted(self.names(pending)), ["IMG_4821.HEIC", "Recording 7.m4a", "roof.txt"])
        self.assertTrue(all(entry["state"] == "seen" for entry in pending["files"]))

    def test_a_file_that_appears_later_is_new_on_its_own(self):
        inbox.list_files(self.conn, self.folder)
        self.drop("fine.pdf", "a parking fine")
        result = inbox.list_files(self.conn, self.folder)
        self.assertEqual(self.names(result), ["fine.pdf"])
        self.assertEqual(result["files"][0]["kind"], "document")

    def test_a_file_still_arriving_is_flagged_and_comes_back_whole(self):
        open(os.path.join(self.folder, "IMG_4822.HEIC"), "w").close()      # the cloud made the name, not the file
        first = inbox.list_files(self.conn, self.folder)
        arriving = [e for e in first["files"] if e["name"] == "IMG_4822.HEIC"]
        self.assertEqual(len(arriving), 1)
        self.assertTrue(arriving[0]["arriving"])
        self.assertIn("not all of it is here yet", inbox.render_list(first))
        self.drop("IMG_4822.HEIC", "now it is really here")
        self.assertEqual(self.names(inbox.list_files(self.conn, self.folder)), ["IMG_4822.HEIC"])

    def test_sync_litter_hidden_files_folders_and_our_own_brief_are_not_offered_to_the_person(self):
        self.drop(".DS_Store")
        self.drop("Icon\r")
        self.drop("photo.jpg.crdownload")
        self.drop("сводка.txt", "our own brief, written by brief.py --to")
        self.drop("brief.txt", "the same, in English")
        os.makedirs(os.path.join(self.folder, "done"))
        self.drop("old.txt", "already sorted last week", folder=os.path.join(self.folder, "done"))
        self.assertEqual(sorted(self.names(inbox.list_files(self.conn, self.folder))),
                         ["IMG_4821.HEIC", "Recording 7.m4a", "roof.txt"])

    def test_the_contents_of_a_file_are_never_read(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root can read anything, so the check proves nothing")
        secret = self.drop("bank.txt", "the card number")
        os.chmod(secret, 0)
        try:
            result = inbox.list_files(self.conn, self.folder)
            self.assertIn("bank.txt", self.names(result))                  # listed by name, never opened
        finally:
            os.chmod(secret, 0o600)


class Marking(Base):
    def setUp(self):
        super().setUp()
        self.drop("fine.pdf", "a parking fine")
        self.drop("roof.txt", "call the roofer")
        inbox.list_files(self.conn, self.folder)

    def test_a_marked_file_leaves_the_pile(self):
        result = inbox.mark(self.conn, "fine.pdf", "task #7", self.folder)
        self.assertEqual((result["ok"], result["file"], result["done"]), (True, "fine.pdf", 1))
        pending = inbox.list_files(self.conn, self.folder, scope="pending")
        self.assertEqual(self.names(pending), ["roof.txt"])
        everything = inbox.list_files(self.conn, self.folder, scope="all")
        self.assertEqual(everything["counts"], {"new": 0, "pending": 1, "done": 1, "total": 2})
        marked = [e for e in everything["files"] if e["name"] == "fine.pdf"][0]
        self.assertEqual((marked["state"], marked["note"]), ("done", "task #7"))

    def test_a_file_already_moved_into_done_can_still_be_marked_by_its_name(self):
        os.makedirs(os.path.join(self.folder, "done"))
        os.replace(os.path.join(self.folder, "fine.pdf"), os.path.join(self.folder, "done", "fine.pdf"))
        result = inbox.mark(self.conn, "fine.pdf", "task #7", self.folder)
        self.assertTrue(result["ok"])
        self.assertEqual(inbox.list_files(self.conn, self.folder, scope="pending")["count"], 1)

    def test_a_file_sorted_the_minute_it_arrived_is_remembered_even_though_it_was_never_listed(self):
        self.drop("clinic.jpg", "a letter from the clinic")
        inbox.mark(self.conn, "clinic.jpg", "task #8", self.folder)
        result = inbox.list_files(self.conn, self.folder)
        self.assertNotIn("clinic.jpg", self.names(result))                 # never offered as new

    def test_a_file_outside_the_folder_is_not_written_down_as_something_from_the_phone(self):
        """`mark "/Users/.../taxes.pdf"` made a row for a file nobody sent from any phone, and our table then
        said the person's own papers had come in from the street and been sorted."""
        outside = os.path.join(self.root, "the persons own taxes.pdf")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("not from any phone")
        with self.assertRaises(tracker.TrackerError) as caught:
            inbox.mark(self.conn, outside, "task #9", self.folder)
        self.assertIn("not in the folder from the phone", str(caught.exception))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM seen_files WHERE path = ?",
                                           (outside,)).fetchone()[0], 0)
        self.assertTrue(os.path.exists(outside))

    def test_marking_something_that_is_not_there_says_so_instead_of_inventing_it(self):
        with self.assertRaises(tracker.TrackerError):
            inbox.mark(self.conn, "nothing-like-this.jpg", "", self.folder)

    def test_marking_does_not_move_delete_or_change_a_single_file(self):
        before = sorted(os.listdir(self.folder))
        inbox.mark(self.conn, "fine.pdf", "task #7", self.folder)
        self.assertEqual(sorted(os.listdir(self.folder)), before)
        with open(os.path.join(self.folder, "roof.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "call the roofer")


class MovingASortedFileIntoDone(Base):
    """The skill used to be handed `Bash(mv *)` and `Bash(mkdir -p *)` - unbounded over every path on the
    computer - and built the command out of a file name that came from a phone. The move lives here now."""

    def setUp(self):
        super().setUp()
        inbox.set_folder(self.conn, self.folder)
        self.drop("fine.pdf", "a parking fine")
        inbox.list_files(self.conn)

    def done_dir(self, name="done"):
        return sorted(os.listdir(os.path.join(self.folder, name)))

    def test_a_sorted_file_moves_into_done_and_is_written_down(self):
        result = inbox.file_done(self.conn, "fine.pdf", "task #7")
        self.assertEqual((result["ok"], result["moved"], result["renamed"]), (True, True, False))
        self.assertEqual(self.done_dir(), ["fine.pdf"])
        self.assertNotIn("fine.pdf", os.listdir(self.folder))
        self.assertEqual(inbox.list_files(self.conn, scope="pending")["count"], 0)
        with open(result["path"], encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "a parking fine")              # moved, not copied and not emptied

    def test_a_name_full_of_shell_characters_is_a_name_and_nothing_else(self):
        self.drop(NASTY, "a note from the street")
        inbox.list_files(self.conn)
        code, _, out, err = self.cli("file-done", NASTY, "--note", "task #9")
        self.assertEqual(code, 0, err)
        # The name is quoted back at us, so "PWNED" is in the output - inside the name, and nowhere else. Take
        # the whole name out of what was printed, and no part of it may be left behind as something that ran.
        self.assertNotIn("PWNED", (out + err).replace(NASTY, ""))
        self.assertEqual(self.done_dir(), [NASTY])
        self.assertNotIn(NASTY, os.listdir(self.folder))
        self.assertEqual(sorted(os.listdir(self.folder)), ["done", "fine.pdf"])   # nothing else was made
        with open(os.path.join(self.folder, "done", NASTY), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "a note from the street")             # moved whole, not emptied

    def test_and_no_script_of_ours_has_a_shell_to_hand_the_name_to(self):
        """The test above runs the script with a list of arguments, which no shell ever sees - so on its own it
        proves the stand is safe, not the product. What makes the product safe is that nothing in `scripts/`
        can reach a shell at all: no `shell=True`, no `os.system`, and the moving done by `os.replace`."""
        for name in sorted(os.listdir(SCRIPTS)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(SCRIPTS, name), encoding="utf-8") as handle:
                source = handle.read()
            for forbidden in ("shell=True", "os.system(", "os.popen(", "getoutput(", "commands.getstatus"):
                self.assertNotIn(forbidden, source, "%s: %s" % (name, forbidden))
        with open(os.path.join(SCRIPTS, "inbox.py"), encoding="utf-8") as handle:
            moving = handle.read()
        self.assertNotIn("import subprocess", moving)
        self.assertIn("os.replace(source, target)", moving)

    def test_a_second_file_of_the_same_name_never_replaces_the_first(self):
        """Two phones both send IMG_0001.HEIC, or the same note is sent twice. `mv` would destroy the first one
        without a word, and the README promises nothing in the folder is ever deleted."""
        inbox.file_done(self.conn, "fine.pdf", "the first one")
        self.drop("fine.pdf", "a different fine, same name")
        inbox.list_files(self.conn)
        result = inbox.file_done(self.conn, "fine.pdf", "the second one")
        self.assertTrue(result["renamed"])
        self.assertEqual(result["new_name"], "fine (2).pdf")
        self.assertEqual(self.done_dir(), ["fine (2).pdf", "fine.pdf"])
        bodies = []
        for name in self.done_dir():
            with open(os.path.join(self.folder, "done", name), encoding="utf-8") as handle:
                bodies.append(handle.read())
        self.assertEqual(sorted(bodies), ["a different fine, same name", "a parking fine"])
        self.assertIn("fine (2).pdf", inbox.render("file-done", result))

    def test_nothing_outside_the_one_folder_can_be_moved(self):
        outside = os.path.join(self.root, "the persons own taxes.pdf")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("not from any phone")
        for name in ("../the persons own taxes.pdf", outside, "../../etc/hosts"):
            with self.assertRaises(tracker.TrackerError, msg=name):
                inbox.file_done(self.conn, name)
        self.assertTrue(os.path.exists(outside))

    def test_a_symbolic_link_out_of_the_folder_is_not_followed(self):
        outside = os.path.join(self.root, "secrets.txt")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("not from any phone")
        os.symlink(outside, os.path.join(self.folder, "innocent.txt"))
        with self.assertRaises(tracker.TrackerError):
            inbox.file_done(self.conn, "innocent.txt")
        self.assertTrue(os.path.exists(outside))

    def test_a_file_somebody_already_moved_by_hand_is_only_written_down(self):
        os.makedirs(os.path.join(self.folder, "done"))
        os.replace(os.path.join(self.folder, "fine.pdf"), os.path.join(self.folder, "done", "fine.pdf"))
        result = inbox.file_done(self.conn, "done/fine.pdf", "task #7")
        self.assertEqual((result["ok"], result["moved"]), (True, False))
        self.assertEqual(self.done_dir(), ["fine.pdf"])

    def test_the_russian_subfolder_works_and_nothing_else_does(self):
        self.assertTrue(inbox.file_done(self.conn, "fine.pdf", into="разобрано")["ok"])
        self.assertEqual(self.done_dir("разобрано"), ["fine.pdf"])
        self.drop("roof.txt", "call the roofer")
        with self.assertRaises(tracker.TrackerError):
            inbox.file_done(self.conn, "roof.txt", into="../..")
        self.assertEqual(self.cli("file-done", "roof.txt", "--into", "anywhere")[0], 2)
        self.assertIn("roof.txt", os.listdir(self.folder))

    def test_a_file_that_is_not_there_is_a_sentence_not_a_traceback(self):
        """And it is the *right* sentence. "There is no such file" and "it could not be moved" are two different
        things to hear, and the second one is frightening in a way the first is not: it says something was
        attempted on a file of theirs and went wrong. Both used to name the file and exit 1, so the check passed
        either way - take the refusal out and the code walked on to `os.replace`, made a `done/` box in their
        folder on the way, and reported the failure of a move that never had anything to move."""
        code, _, _, err = self.cli("file-done", "ghost.jpg")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("no file called ghost.jpg", err)
        self.assertNotIn("could not be moved", err)
        self.assertEqual(os.listdir(self.folder), ["fine.pdf"])        # and no box of ours was made on the way

    def test_the_box_for_sorted_files_is_checked_where_it_lands_and_not_only_where_it_came_from(self):
        """`_inside` was asked about the source and never about the target, and the only thing standing between
        a file and the outside of the folder was our own tuple of two words. Add `".."` to it - one line, no test
        anywhere went red - and `file-done --into ..` carried the file out of the folder the person named."""
        was = inbox.DONE_DIRS
        inbox.DONE_DIRS = was + ("..",)
        try:
            with self.assertRaises(tracker.TrackerError) as caught:
                inbox.file_done(self.conn, "fine.pdf", into="..")
        finally:
            inbox.DONE_DIRS = was
        self.assertIn("fine.pdf", os.listdir(self.folder))             # still where the phone put it
        self.assertFalse(os.path.exists(os.path.join(self.root, "fine.pdf")))
        self.assertIn("done", str(caught.exception))

    def test_moving_needs_a_folder_to_have_been_named(self):
        other = inbox.connect(os.path.join(self.root, "other.db"))
        try:
            with self.assertRaises(tracker.TrackerError):
                inbox.file_done(other, "fine.pdf")
        finally:
            other.close()


class TheFolderIsRemembered(Base):
    def test_set_then_get(self):
        self.assertIsNone(inbox.folder(self.conn)["folder"])
        result = inbox.folder(self.conn, self.folder)
        self.assertEqual((result["folder"], result["exists"]), (self.folder, True))
        self.assertEqual(inbox.folder(self.conn)["folder"], self.folder)

    def test_a_remembered_folder_is_the_one_used_when_none_is_named(self):
        inbox.folder(self.conn, self.folder)
        self.drop("fine.pdf", "a parking fine")
        self.assertEqual(self.names(inbox.list_files(self.conn)), ["fine.pdf"])

    def test_setting_it_again_replaces_it_rather_than_keeping_both(self):
        other = os.path.join(self.root, "Dropbox phone")
        os.makedirs(other)
        inbox.folder(self.conn, self.folder)
        inbox.folder(self.conn, other)
        self.assertEqual(inbox.folder(self.conn)["folder"], other)
        rows = self.conn.execute("SELECT COUNT(*) FROM inbox_settings WHERE key = ?",
                                 (inbox.FOLDER_KEY,)).fetchone()[0]
        self.assertEqual(rows, 1)

    def test_a_folder_that_the_cloud_has_not_synced_yet_may_still_be_remembered(self):
        later = os.path.join(self.root, "not synced yet")
        result = inbox.folder(self.conn, later)
        self.assertEqual((result["ok"], result["exists"]), (True, False))
        self.assertEqual(inbox.folder(self.conn)["folder"], later)

    def test_no_folder_and_no_argument_is_an_answer_not_an_error(self):
        result = inbox.list_files(self.conn)
        self.assertEqual((result["ok"], result["folder"], result["count"]), (True, None, 0))
        self.assertIn("No folder from the phone has been named", inbox.render_list(result))

    def test_the_get_flag_is_really_read_and_not_working_by_accident(self):
        self.cli("folder", "--set", self.folder)
        code, data, out, _ = self.cli("folder", "--get", "--json")
        self.assertEqual((code, data["folder"]), (0, self.folder))
        self.assertIn(self.folder, self.cli("folder", "--get")[2])
        self.assertEqual(self.cli("folder", "--get", "--set", self.folder)[0], 2)   # one question at a time


class TheFolderIsArguedWith(Base):
    """Pointed at `/`, at the home folder or at `~/Documents`, the list offers the person their own files as
    "what came from your phone", and the skill then offers to move them into `~/done/`."""

    def test_the_root_the_home_folder_and_documents_are_all_refused(self):
        for path in ("/", "~", "~/", "~/Documents", os.path.expanduser("~"), os.path.dirname(
                os.path.realpath(os.path.expanduser("~")))):
            with self.assertRaises(tracker.TrackerError, msg=path):
                inbox.set_folder(self.conn, path)
        self.assertIsNone(inbox.folder(self.conn)["folder"])               # and nothing was remembered

    def test_the_refusal_says_what_to_do_instead_and_names_no_commands(self):
        for lang, expected in (("en", "Google Drive or Dropbox"), ("ru", "Google Диске или Dropbox")):
            try:
                inbox.set_folder(self.conn, "~", lang)
                self.fail("the home folder was accepted")
            except tracker.TrackerError as exc:
                self.assertIn(expected, str(exc))
                self.assertNotIn("inbox.py", str(exc))

    def test_a_folder_of_its_own_one_level_down_is_fine(self):
        deep = os.path.join(self.root, "Dropbox", "From the phone")
        os.makedirs(deep)
        self.assertEqual(inbox.set_folder(self.conn, deep)["folder"], deep)

    def test_a_folder_holding_somebodys_whole_life_is_refused_the_first_time(self):
        crowded = os.path.join(self.root, "Documents copy")
        os.makedirs(crowded)
        for number in range(inbox.CROWDED_FOLDER + 1):
            open(os.path.join(crowded, "paper %03d.pdf" % number), "w").close()
        with self.assertRaises(tracker.TrackerError) as caught:
            inbox.set_folder(self.conn, crowded)
        self.assertIn(str(inbox.CROWDED_FOLDER + 1), str(caught.exception))
        self.assertIsNone(inbox.folder(self.conn)["folder"])

    def test_the_refusal_offers_a_way_out_that_works_for_the_phone_folder_too(self):
        """The sentence said one thing only: "make a folder inside it for the phone, and name that one instead".
        For somebody's `Documents` that is the right advice. For the folder their phone has been filling for a
        year - which is the one they would be naming - it is advice to start again somewhere else, and it says
        nothing about the box this very script makes (`done/`) or about simply putting the files away by hand."""
        crowded = os.path.join(self.root, "Phone photos")
        os.makedirs(crowded)
        for number in range(inbox.CROWDED_FOLDER + 1):
            open(os.path.join(crowded, "IMG_%04d.HEIC" % number), "w").close()
        for lang, box, by_hand in (("en", "done folder inside it", "by hand"),
                                   ("ru", "разобрано внутри неё", "руками")):
            with self.assertRaises(tracker.TrackerError) as caught:
                inbox.set_folder(self.conn, crowded, lang)
            said = str(caught.exception)
            self.assertIn(box, said, lang)
            self.assertIn(by_hand, said, lang)
            self.assertNotIn("inbox.py", said)
        self.assertNotIn("Заведите внутри неё отдельную папку", inbox.WORDS["ru"]["crowded"])

    def test_a_file_is_not_a_folder(self):
        paper = self.drop("fine.pdf", "a parking fine")
        with self.assertRaises(tracker.TrackerError):
            inbox.set_folder(self.conn, paper)

    def test_what_is_remembered_is_the_real_path(self):
        link = os.path.join(self.root, "shortcut")
        os.symlink(self.folder, link)
        self.assertEqual(inbox.set_folder(self.conn, link)["folder"], self.folder)

    def test_a_folder_named_on_the_line_is_argued_with_too(self):
        for args in (["list", "--folder", "/"], ["list", "--folder", "~"]):
            code, _, _, err = self.cli(*args)
            self.assertEqual(code, 1, args)
            self.assertNotIn("Traceback", err)

    def crowd(self, where, how_many=None):
        os.makedirs(where, exist_ok=True)
        for number in range(how_many or (inbox.CROWDED_FOLDER + 50)):
            open(os.path.join(where, "paper %03d.pdf" % number), "w").close()
        return where

    def test_a_folder_named_on_the_line_is_counted_too_and_not_only_the_one_we_remember(self):
        """`how_crowded` was asked only when a folder was being *remembered*. `--folder` - a flag the skill
        documents and uses - walked past it: 250 of the person's own papers came back as "new from the phone",
        and `file-done --folder` would then have moved them into a `done/` box of ours. A folder named on the
        line is a folder being named, whichever command names it."""
        counted = str(inbox.CROWDED_FOLDER + 1)                             # we stop counting one past the line
        crowded = self.crowd(os.path.join(self.root, "Documents copy"))
        for call in (lambda: inbox.list_files(self.conn, crowded),
                     lambda: inbox.mark(self.conn, "paper 001.pdf", "", crowded),
                     lambda: inbox.file_done(self.conn, "paper 001.pdf", path=crowded)):
            with self.assertRaises(tracker.TrackerError) as caught:
                call()
            self.assertIn(counted, str(caught.exception))
        code, _, out, err = self.cli("list", "--folder", crowded)
        self.assertEqual(code, 1)
        self.assertNotIn("paper 001.pdf", out)
        self.assertIn(counted, err)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM seen_files").fetchone()[0], 0)
        self.assertFalse(os.path.exists(os.path.join(crowded, "done")))     # and nothing of ours was made in it

    def test_the_home_folder_is_refused_on_the_line_for_moving_as_well_as_for_looking(self):
        for call in (lambda: inbox.list_files(self.conn, "~"),
                     lambda: inbox.mark(self.conn, "anything.pdf", "", "~"),
                     lambda: inbox.file_done(self.conn, "anything.pdf", path="~")):
            with self.assertRaises(tracker.TrackerError):
                call()

    def test_the_folder_they_already_named_is_never_locked_for_having_filled_up(self):
        """The check that argues with a folder being *named* was moved onto every command, and the folder from
        the phone became a wall the day ordinary use took it past two hundred things: `list`, `mark` and
        `file-done` all refused, including the one command that makes the pile smaller. There was no way out
        through the product, and the sentence the person read - make a folder inside it for the phone and name
        that one - was about the folder their phone was already sending to.

        So: how full it is, only where a folder is named. What kind of path it is, always (the test below)."""
        inbox.set_folder(self.conn, self.folder)
        self.crowd(self.folder, inbox.CROWDED_FOLDER + 5)
        self.drop("fine.pdf", "a parking fine")
        listed = inbox.list_files(self.conn)
        self.assertTrue(listed["ok"])
        self.assertIn("fine.pdf", self.names(listed))
        self.assertTrue(inbox.mark(self.conn, "paper 001.pdf", "task #7")["ok"])
        moved = inbox.file_done(self.conn, "fine.pdf", "task #8")        # the way out has to keep working
        self.assertEqual((moved["ok"], moved["moved"]), (True, True))
        self.assertEqual(os.listdir(os.path.join(self.folder, "done")), ["fine.pdf"])
        code, _, out, err = self.cli("list", "--folder", self.folder)     # named on the line, but the same folder
        self.assertEqual(code, 0, err)
        code, _, _, err = self.cli("file-done", "paper 002.pdf", "--folder", self.folder)
        self.assertEqual(code, 0, err)

    def test_but_what_kind_of_path_it_is_is_still_argued_with_on_every_command(self):
        """The crowd question moved; this one did not. A remembered folder that is now the home folder, or a
        file, or gone above the line we will not cross, is refused on `list`, on `mark` and on `file-done`."""
        for bad in (os.path.expanduser("~"), os.sep, os.path.join(os.path.expanduser("~"), "Documents")):
            self.conn.execute("INSERT OR REPLACE INTO inbox_settings (key, value, updated_at) VALUES (?, ?, '')",
                              (inbox.FOLDER_KEY, bad))
            self.conn.commit()
            for call in (lambda: inbox.list_files(self.conn),
                         lambda: inbox.mark(self.conn, "anything.pdf"),
                         lambda: inbox.file_done(self.conn, "anything.pdf")):
                with self.assertRaises(tracker.TrackerError, msg=bad):
                    call()


class BothLanguages(Base):
    """Everything else in the product speaks to the person in their own language; this did not, and it printed a
    fixed-width table at them while its own skill says never to show one."""

    def setUp(self):
        super().setUp()
        self.drop("IMG_4821.HEIC", "a photograph of a letter")
        self.drop("Recording 7.m4a", "twenty seconds")

    def test_the_same_files_in_the_persons_own_words(self):
        result = inbox.list_files(self.conn, self.folder)
        english = inbox.render_list(result, "en")
        russian = inbox.render_list(result, "ru")
        self.assertIn("photo - IMG_4821.HEIC", english)
        self.assertIn("voice recording - Recording 7.m4a", english)
        self.assertIn("фотография - IMG_4821.HEIC", russian)
        self.assertIn("голосовая запись - Recording 7.m4a", russian)
        self.assertNotIn("фотография", english)
        self.assertNotIn("photo -", russian)

    def test_no_command_is_ever_shown_to_the_person(self):
        empty = inbox.list_files(self.conn)                                # no folder named at all
        self.drop("IMG_4822.HEIC")                                         # zero bytes: still arriving
        seen = inbox.list_files(self.conn, self.folder)
        inbox.list_files(self.conn, self.folder)
        pending_hint = inbox.render_list(inbox.list_files(self.conn, self.folder), "ru")
        for lang in ("en", "ru"):
            for text in (inbox.render_list(empty, lang), inbox.render_list(seen, lang), pending_hint,
                         inbox.render("folder", {"folder": None, "exists": False}, lang)):
                self.assertNotIn("inbox.py", text)
                self.assertNotIn("--", text)

    def test_the_list_is_lines_and_not_a_table(self):
        """With two names of much the same length, a padded table and a plain list look alike, so the check had
        nothing to catch. One very short name and one very long one tell them apart: a table pads the short one
        out to the width of the long one."""
        self.drop("a.txt", "one line")
        self.drop("Scan of the letter from the housing office, 24 September 2026.pdf", "a letter")
        result = inbox.list_files(self.conn, self.folder)
        text = inbox.render_list(result, "ru")
        lines = text.splitlines()
        self.assertEqual(len(lines), 1 + result["count"])                  # one heading, one line per file
        for line in lines[1:]:
            self.assertTrue(line.startswith("  "), line)
            self.assertNotIn("   ", line)                                  # no columns padded out with spaces
            self.assertNotIn("|", line)
            self.assertIn(" - ", line)

    def test_the_language_reaches_the_command_line(self):
        self.cli("folder", "--set", self.folder)
        self.assertIn("фотография", self.cli("list", "--lang", "ru")[2])
        self.assertEqual(self.cli("--lang", "klingon", "list")[0], 2)

    def test_a_refusal_speaks_the_same_language(self):
        self.cli("folder", "--set", self.folder)
        code, _, _, err = self.cli("mark", "ghost.jpg", "--lang", "ru")
        self.assertEqual(code, 1)
        self.assertIn("ghost.jpg", err)
        self.assertIn("нет", err)


class NothingFallsOver(Base):
    def test_a_folder_that_is_not_there_is_a_sentence_not_a_crash(self):
        result = inbox.list_files(self.conn, os.path.join(self.root, "no such folder"))
        self.assertEqual((result["ok"], result["exists"], result["count"]), (True, False, 0))
        self.assertIn("not on this computer", inbox.render_list(result))

    def test_the_command_line_survives_a_folder_that_is_not_there(self):
        for args in (["list", "--folder", os.path.join(self.root, "gone")],
                     ["list", "--folder", os.path.join(self.root, "gone"), "--json"],
                     ["list"], ["folder", "--get"]):
            code, _, out, err = self.cli(*args)
            self.assertEqual(code, 0, args)
            self.assertNotIn("Traceback", err)
            self.assertTrue(out.strip(), args)

    def test_a_file_named_in_the_folder_but_gone_by_the_time_we_look_is_skipped(self):
        self.drop("fine.pdf", "a parking fine")
        missing = os.path.join(self.folder, "vanished.txt")
        with open(missing, "w", encoding="utf-8") as handle:
            handle.write("here for a moment")
        os.remove(missing)
        self.assertEqual(self.names(inbox.list_files(self.conn, self.folder)), ["fine.pdf"])

    def test_an_older_database_really_gets_the_new_tables(self):
        plain = os.path.join(self.root, "old.db")
        old = tracker.connect(plain)                                       # a database from before this feature
        tracker.add(old, "Refund", "the money is back on the card")
        self.assertEqual(self.tables(old), [])                             # neither of ours is there yet
        old.close()
        conn = inbox.connect(plain)
        try:
            self.assertEqual(self.tables(conn), ["inbox_settings", "seen_files"])
            inbox.migrate(conn)                                            # twice is harmless
            self.assertEqual(self.tables(conn), ["inbox_settings", "seen_files"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
            inbox.set_folder(conn, self.folder)                            # and both tables really work
            self.drop("fine.pdf", "a parking fine")
            self.assertEqual(self.names(inbox.list_files(conn)), ["fine.pdf"])
        finally:
            conn.close()

    def test_a_database_held_by_the_other_process_is_a_sentence_not_a_traceback(self):
        """A routine run and a live session share one file. `migrate` used to swallow the failure and hand back
        a database with no tables in it; the next line was then a Python traceback in front of a person of 68."""
        shared = os.path.join(self.root, "shared.db")
        other = tracker.connect(shared)
        other.execute("BEGIN EXCLUSIVE")                                   # the routine run, mid-write
        patience = tracker.BUSY_WAIT_SECONDS
        tracker.BUSY_WAIT_SECONDS = 0.2
        try:
            for lang, expected in (("en", "busy"), ("ru", "занят")):
                with self.assertRaises(tracker.TrackerError) as caught:
                    inbox.connect(shared, lang)
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn("sqlite3", str(caught.exception))
        finally:
            tracker.BUSY_WAIT_SECONDS = patience
            other.rollback()
            other.close()

    def test_a_table_of_ours_that_is_not_a_table_is_refused_and_not_handed_over(self):
        """`CREATE TABLE IF NOT EXISTS inbox_settings` runs happily and does nothing at all on a database where
        `inbox_settings` is somebody's view - no index of ours touches that one, so nothing raises. Without the
        check that the tables are really there afterwards, the very next statement is a traceback."""
        shadowed = os.path.join(self.root, "shadowed.db")
        plain = sqlite3.connect(shadowed)
        plain.executescript("CREATE TABLE x (id INTEGER); CREATE VIEW inbox_settings AS SELECT * FROM x;")
        plain.commit()
        plain.close()
        for lang, expected in (("en", "not a Chasecall task file"), ("ru", "не файл дел")):
            with self.assertRaises(tracker.TrackerError) as caught:
                inbox.connect(shadowed, lang)
            self.assertIn(expected, str(caught.exception))
            self.assertNotIn("sqlite3", str(caught.exception))
        code, _, _, err = self.cli("list", env_extra={"CHASECALL_DB": shadowed})
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)

    def tables(self, conn):
        return sorted(row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?)", inbox.TABLES).fetchall())


class CommandLine(Base):
    def test_the_whole_round_trip_from_the_command_line(self):
        self.drop("fine.pdf", "a parking fine")
        self.drop("roof.txt", "call the roofer")
        code, _, out, _ = self.cli("folder", "--set", self.folder)
        self.assertEqual(code, 0)
        self.assertIn(self.folder, out)

        code, data, _, _ = self.cli("list", "--json")
        self.assertEqual((code, data["count"], data["exists"]), (0, 2, True))
        self.assertEqual(sorted(entry["name"] for entry in data["files"]), ["fine.pdf", "roof.txt"])
        self.assertEqual(sorted(data["counts"]), ["done", "new", "pending", "total"])

        code, data, _, _ = self.cli("--json", "list")                      # the flag works on either side
        self.assertEqual((code, data["count"]), (0, 0))

        code, _, out, _ = self.cli("mark", "fine.pdf", "--note", "task #7")
        self.assertEqual(code, 0)
        self.assertIn("fine.pdf", out)
        self.assertIn("not touched", out)
        self.assertIn("fine.pdf", os.listdir(self.folder))                 # marked, and still where it was

        code, data, _, _ = self.cli("list", "--pending", "--json")
        self.assertEqual([entry["name"] for entry in data["files"]], ["roof.txt"])

        code, data, _, _ = self.cli("file-done", "roof.txt", "--note", "task #8", "--json")
        self.assertEqual((code, data["moved"]), (0, True))
        self.assertEqual(os.listdir(os.path.join(self.folder, "done")), ["roof.txt"])

        code, data, _, _ = self.cli("list", "--all", "--json")
        self.assertEqual([entry["name"] for entry in data["files"]], ["fine.pdf"])

    def test_marking_something_unknown_fails_in_one_readable_line(self):
        self.cli("folder", "--set", self.folder)
        code, _, out, err = self.cli("mark", "ghost.jpg")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("no file called", err)
        code, data, out, _ = self.cli("mark", "ghost.jpg", "--json")
        self.assertEqual((code, data["ok"]), (1, False))
        self.assertIn("error", data)

    def test_the_json_shape_is_the_same_on_every_command_that_has_one(self):
        """`--json` is a deliberate part of this interface and not a leftover: it is how a session reads a
        *number* (how many are new, was it renamed, where did it go) instead of parsing a sentence written for a
        person in one of two languages. The skills print the sentences; the flag is here for when a count has to
        be right. Whether every flag a skill names exists is checked, for all of them at once, against the
        parsers themselves in `tests/test_repo.py`."""
        self.drop("fine.pdf", "a parking fine")
        for args in (["list", "--all", "--folder", self.folder],
                     ["list", "--pending", "--folder", self.folder],
                     ["mark", "fine.pdf", "--folder", self.folder],
                     ["folder", "--get"]):
            code, data, out, err = self.cli(*(args + ["--json"]))
            self.assertEqual((code, data["ok"]), (0, True), args + [err])
            self.assertEqual(err, "", args)
            self.assertEqual(json.loads(out), data)                        # nothing but JSON on the output


if __name__ == "__main__":
    unittest.main()
