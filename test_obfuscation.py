import json
import unittest
from unittest.mock import patch
import bot


class ObfuscationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((bot.ROOT / 'config.json').read_text(encoding='utf-8'))
        cls.rules = bot.compile_rules(cls.config)

    def test_requested_examples(self):
        for text in ['N1GA', 'nig@', 'n1g@', 'N1GA!', 'n!gga']:
            with self.subTest(text=text):
                self.assertTrue(bot.is_blocked(text, self.rules))

    def test_separators_repetitions(self):
        for text in ['n.i.g.g.a', 'n i g g a', 'n_i_g_g_a', 'nnniiiggggaaa', 'n.i.g.g.e.r']:
            with self.subTest(text=text):
                self.assertTrue(bot.is_blocked(text, self.rules))

    def test_unicode(self):
        for text in ['nіііggа', 'ＮＩＧＧＡ', 'n\u200bigga', 'n\u0301igga', 'nіggа']:
            with self.subTest(text=text):
                self.assertTrue(bot.is_blocked(text, self.rules))

    def test_neutral(self):
        for text in ['Привет всем!', 'Nigeria', 'Niger', 'Нигер', 'Нигера', 'Scunthorpe', 'class assignment',
                     'Поговорим про политику', 'Кот спит', 'Это нигерийская музыка', 'Спасибо за стрим',
                     'Новая игра вышла вчера', 'Я изучаю религии мира', 'Сегодня мы обсуждаем историю']:
            with self.subTest(text=text):
                self.assertFalse(bot.is_blocked(text, self.rules))

    def test_language_groups(self):
        for text in ['пидор', 'pidor', 'motherfucker', 'Hurensohn', 'connard', 'gilipollas', 'caralho', 'vaffanculo']:
            with self.subTest(text=text):
                self.assertTrue(bot.is_blocked(text, self.rules))

    def test_disabled_obfuscation(self):
        rules=bot.compile_rules({'moderation':{'blocked_words':['nigga'], 'anti_obfuscation':False}})
        self.assertFalse(bot.is_blocked('N1GA',rules))
        self.assertTrue(bot.is_blocked('nigga',rules))

    def test_builtin_disabled(self):
        rules=bot.compile_rules({'moderation':{'use_builtin_dictionary':False, 'blocked_words':['тестудаления']}})
        self.assertFalse(bot.is_blocked('nigga',rules))
        self.assertTrue(bot.is_blocked('тестудаления',rules))

    def test_phrase_boundaries(self):
        rules=bot.compile_rules({'moderation':{'blocked_phrases':['bad phrase'], 'anti_obfuscation':True}})
        self.assertTrue(bot.is_blocked('b.a.d p.h.r.a.s.e',rules))
        self.assertFalse(bot.is_blocked('notbad phrasebook',rules))

    def test_every_dictionary_entry(self):
        data=json.loads((bot.ROOT / 'blocklist.json').read_text(encoding='utf-8'))
        for group in data['languages'].values():
            for text in group['words'] + group['phrases']:
                with self.subTest(text=text):
                    self.assertTrue(bot.is_blocked(text,self.rules))

    def test_invalid_dictionary_rejected(self):
        with patch('bot.dictionary_terms',side_effect=ValueError('invalid dictionary')):
            with self.assertRaises(ValueError):
                bot.compile_rules(self.config)


if __name__ == '__main__':
    unittest.main()
