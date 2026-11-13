import unittest
from urllib.parse import unquote

from app.services.export_filename import export_disposition, results_filename


class ExportFilenameTests(unittest.TestCase):
    def test_titles_produce_portable_names_without_losing_unicode(self):
        for title, expected in [
            ("AI Engineer", "AI Engineer-results.csv"),
            ('  AI / Engineer: "Europe"?  ', "AI Engineer Europe-results.csv"),
            ("Développeur 日本語", "Développeur 日本語-results.csv"),
            ("../CON\\..\r\nInjected: value", "CON .. Injected value-results.csv"),
            ("... /:*? ", "assessment-results.csv"),
        ]:
            with self.subTest(title=title):
                self.assertEqual(results_filename(title),expected)
                header=export_disposition(title)
                self.assertNotIn("\r",header)
                self.assertNotIn("\n",header)
                header.encode("ascii")
                self.assertEqual(unquote(header.split("filename*=UTF-8''")[1]),expected)
        self.assertEqual(results_filename("😀"*120),"😀"*100+"-results.csv")
