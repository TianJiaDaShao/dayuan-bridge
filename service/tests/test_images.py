import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from dayuan.images import image_urls,download_images
class ImagesTests(unittest.TestCase):
 def test_only_expected_https_hosts_and_deduplication(self):
  text='https://wdcdn.qpic.cn/a https://evil.example/a https://qpic.cn.evil.example/a https://wdcdn.qpic.cn/a'
  self.assertEqual(image_urls(text),['https://wdcdn.qpic.cn/a'])
 def test_invalid_payload_is_not_saved(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return b'<html>login</html>'
  with tempfile.TemporaryDirectory() as d,patch('urllib.request.OpenerDirector.open',return_value=Response()):
   result=download_images('https://wdcdn.qpic.cn/a',d)
   self.assertFalse(result['files']);self.assertTrue(result['errors']);self.assertFalse(list(Path(d).iterdir()))
