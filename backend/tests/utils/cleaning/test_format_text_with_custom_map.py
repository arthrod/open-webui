import unittest
import logging
from backend.utils.cleaning.format_text_with_custom_map import replace_text_in_files, load_cmap_custom

class TestFormatTextWithCustomMap(unittest.TestCase):

    def setUp(self):
        self.sample_text = "(CID:431) is replaced with ff"
        self.expected_text = "ff is replaced with ff"
        self.format_file_name = 'cmap_custom.csv'
        self.replacement_dict = {'(CID:431)': 'ff'}

    def test_replace_text_in_files(self):
        result = replace_text_in_files(self.sample_text, self.format_file_name)
        print(f'result: {result}')
        self.assertEqual(result, self.expected_text)

    def test_load_cmap_custom(self):
        result = load_cmap_custom(self.format_file_name)
        print(f'result: {result}')
        self.assertEqual(result, self.replacement_dict)

if __name__ == '__main__':
    unittest.main()
