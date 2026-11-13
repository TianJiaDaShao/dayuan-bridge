"""Download original image URLs as the ordinary CLI user."""
import hashlib,os,re,tempfile,urllib.parse,urllib.request
from pathlib import Path

MAX_IMAGE=20*1024*1024

def image_urls(text):
    urls=[]
    for url in re.findall(r'https://[^\s<>`"\]\)]+',text):
        host=(urllib.parse.urlsplit(url).hostname or '').lower()
        if host=='qpic.cn' or host.endswith('.qpic.cn'):
            if url not in urls:urls.append(url)
    return urls

class ImageRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not image_urls(newurl):raise ValueError('UNTRUSTED_IMAGE_REDIRECT')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download_images(text,directory):
    urls=image_urls(text)
    directory=Path(directory).expanduser();directory.mkdir(parents=True,exist_ok=True)
    opener=urllib.request.build_opener(ImageRedirect());files=[];errors=[]
    for index,url in enumerate(urls,1):
        try:
            with opener.open(url,timeout=30) as response:data=response.read(MAX_IMAGE+1)
            if len(data)>MAX_IMAGE:raise ValueError('IMAGE_TOO_LARGE')
            ext='png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'jpg' if data.startswith(b'\xff\xd8\xff') else 'gif' if data.startswith((b'GIF87a',b'GIF89a')) else 'webp' if data[:4]==b'RIFF' and data[8:12]==b'WEBP' else None
            if not ext:raise ValueError('NOT_A_SUPPORTED_IMAGE')
            digest=hashlib.sha256(data).hexdigest();path=directory/('image-%02d-%s.%s'%(index,digest[:12],ext))
            fd,tmp=tempfile.mkstemp(prefix='.image-',dir=str(directory))
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(data)
                os.replace(tmp,path)
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
            files.append({'path':str(path.resolve()),'bytes':len(data),'sha256':digest})
        except Exception as exc:errors.append({'image_index':index,'error':type(exc).__name__})
    return {'files':files,'errors':errors,'url_count':len(urls)}
