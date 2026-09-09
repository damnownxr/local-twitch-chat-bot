import unittest
from unittest.mock import patch, Mock
import bot

class FilterTests(unittest.TestCase):
    def rules(self, **kwargs):
        return bot.compile_rules({'moderation':kwargs})

    def test_word_case(self):
        r=self.rules(blocked_words=['кот'])
        self.assertTrue(bot.is_blocked('Это КОТ!',r))
        self.assertFalse(bot.is_blocked('котик и скот',r))

    def test_phrase(self):
        r=self.rules(blocked_phrases=['запретная тема'])
        self.assertTrue(bot.is_blocked('Вот запретная    тема!',r))
        self.assertFalse(bot.is_blocked('незапретная тема',r))

    def test_substring(self):
        self.assertTrue(bot.is_blocked('котик',self.rules(blocked_substrings=['кот'])))

    def test_zero_width(self):
        self.assertTrue(bot.is_blocked('ко\u200bт',self.rules(blocked_words=['кот'])))

    def test_empty(self):
        self.assertFalse(bot.is_blocked('текст',self.rules(blocked_words=['  '])))

    def test_regex_is_literal(self):
        r=self.rules(blocked_substrings=['a.b'])
        self.assertTrue(bot.is_blocked('a.b',r))
        self.assertFalse(bot.is_blocked('axb',r))

    def test_unicode_width(self):
        self.assertTrue(bot.is_blocked('ＢＡＤ', self.rules(blocked_words=['bad'])))

    def test_irc(self):
        t,p,c,a,s=bot.parse_irc('@id=abc;user-id=12;mod=0 :x!x@x PRIVMSG #demo :привет : мир')
        self.assertEqual((t['id'],c,a,s),('abc','PRIVMSG',['#demo'],'привет : мир'))

    def test_roomstate(self):
        self.assertEqual(bot.parse_irc('@room-id=1 :tmi.twitch.tv ROOMSTATE #demo')[2],'ROOMSTATE')

class ApiTests(unittest.TestCase):
    @patch.dict('os.environ',{'TWITCH_CLIENT_ID':'test','TWITCH_CLIENT_SECRET':'secret'})
    @patch('bot.requests.request')
    def test_delete_preserves_message_id(self, request):
        response=Mock(status_code=204,ok=True,content=b'')
        request.return_value=response
        c=bot.Twitch()
        c.tokens={'access_token':'fake'}
        c.expires_at=float('inf')
        params={'broadcaster_id':'1','moderator_id':'2','message_id':'3'}
        self.assertEqual(c.api('DELETE','moderation/chat',params=params),{})
        self.assertEqual(request.call_args.kwargs['params'],params)
        self.assertEqual(request.call_args.args[0],'DELETE')

    @patch.dict('os.environ',{'TWITCH_CLIENT_ID':'test','TWITCH_CLIENT_SECRET':'secret'})
    @patch('bot.requests.request')
    def test_send_body(self, request):
        request.return_value=Mock(status_code=200,ok=True,content=b'x')
        request.return_value.json.return_value={'data':[{'is_sent':True}]}
        c=bot.Twitch()
        c.tokens={'access_token':'fake'}
        c.expires_at=float('inf')
        body={'broadcaster_id':'1','sender_id':'2','message':'привет'}
        self.assertTrue(c.api('POST','chat/messages',body=body)['data'][0]['is_sent'])
        self.assertEqual(request.call_args.kwargs['json'],body)

if __name__=='__main__':
    unittest.main()
