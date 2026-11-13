"""Fixed Objective-C operations. No cached pointers or injected shell commands."""
import json


def literal(value):
    # UTF-8 literals preserve non-BMP characters (JSON surrogate escapes are
    # invalid universal character names in Clang's Objective-C parser).
    return "@" + json.dumps(value, ensure_ascii=False)


def sel(name):
    return '((void*(*)(const char*))sel_registerName)(%s)' % json.dumps(name)


def obj(receiver, selector):
    return '((void*(*)(void*,void*))objc_msgSend)((void*)(%s),%s)' % (receiver, sel(selector))


def boolean(receiver, selector):
    return '((unsigned char(*)(void*,void*))objc_msgSend)((void*)(%s),%s)' % (receiver, sel(selector))


def has(receiver, selector):
    return '((unsigned char(*)(void*,void*,void*))objc_msgSend)((void*)(%s),%s,%s)' % (receiver, sel('respondsToSelector:'), sel(selector))


def contains(receiver, text):
    return '((unsigned char(*)(void*,void*,void*))objc_msgSend)((void*)(%s),%s,(void*)%s)' % (receiver, sel('containsString:'), literal(text))


# A retained, windowless controller belongs to the bridge, not to the user's
# foreground assistant window. Runtime selectors are resolved on every call.
HEADLESS_KEY = 'dayuan.bridge.headless.v1'
APP = '((void*(*)(const char*))objc_getClass)("NSApplication")'
HEAD = """
void *appcls=APP_CLASS,*app=0,*key=HEADLESS_SEL;
if(appcls && APP_HAS)app=APP_SHARED;
void *main=app?((void*(*)(void*,void*))objc_getAssociatedObject)(app,key):0;
""".replace('APP_CLASS', APP).replace('HEADLESS_SEL', sel(HEADLESS_KEY)).replace('APP_HAS', has('appcls','sharedApplication')).replace('APP_SHARED',obj('appcls','sharedApplication'))
RESOLVE = 'void *cls=((void*(*)(const char*))objc_getClass)("WEWWeClawChatMainViewController");' + HEAD
# The Foundation-only test fixture has no NSApplication. Never fall back to
# the foreground conversation in the real AppKit client.
RESOLVE += 'if(!appcls && cls && %s)main=%s;' % (has('cls','existingInstance'),obj('cls','existingInstance'))
RESOLVE += 'void *chat=0,*view=0,*sender=0,*list=0,*items=0;'
for target, source, selector in [
    ('chat', 'main', 'currentChatViewController'),
    ('view', 'chat', 'clawView'),
    ('sender', 'view', 'inputVC'),
    ('list', 'chat', 'msgListCtrl'),
    ('items', 'list', 'dataArray'),
]:
    RESOLVE += 'if(%s && %s) %s=%s;\n' % (source, has(source, selector), target, obj(source, selector))


def prepare_expression():
    code='void *cls=((void*(*)(const char*))objc_getClass)("WEWWeClawChatMainViewController");'+HEAD
    code+='if(app && !main && cls && %s){main=%s;if(main){((void(*)(void*,void*,void*,unsigned long))objc_setAssociatedObject)(app,key,main,1);%s;}}' % (has('cls','new'),obj('cls','new'),obj('main','release'))
    code+='void *v=0,*left=0,*list=0,*chat=0;'
    for target,source,selector in [('v','main','view'),('left','main','leftVC'),('list','left','convListCtrl'),('chat','main','currentChatViewController')]:
        code+='if(%s && %s)%s=%s;' % (source,has(source,selector),target,obj(source,selector))
    code+='if(list && !chat && %s){%s;}' % (has('list','wew_selectNext'),obj('list','wew_selectNext'))
    return '({'+code+' (unsigned long long)(main?1:0);})'


def window_expression():
    return '({'+RESOLVE+' void *v=main?'+obj('main','view')+':0; (unsigned long long)(v?'+obj('v','window')+':0);})'


def doctor_expression():
    # A decimal bit mask reports presence only, never object addresses or content.
    return '({%s (unsigned long long)((cls?1:0)|(main?2:0)|(chat?4:0)|(view?8:0)|(sender?16:0)|(items?32:0));})' % RESOLVE


def session_expression():
    return '({%s void *s=0;if(main && %s)s=%s; (unsigned long long)(s?%s:0);})' % (
        RESOLVE, has('main', 'currentConversationContextId'), obj('main', 'currentConversationContextId'), obj('s', 'UTF8String'))


def submit_expression(prompt):
    selector = 'wew_sendBypassTextStorageWithText:subjectEntry:'
    return '({%s unsigned long long ok=0;if(sender && %s){((void(*)(void*,void*,void*,void*))objc_msgSend)(sender,%s,(void*)%s,(void*)0);ok=1;}ok;})' % (
        RESOLVE, has('sender', selector), sel(selector), literal(prompt))


def result_expression(begin, end):
    # Reject our own outgoing prompt, which also contains the two delimiters.
    # Inspect candidate strings inside the client; export only a matching answer.
    return '''({%s
unsigned long long found=0;
if(items){
 unsigned long long n=((unsigned long long(*)(void*,void*))objc_msgSend)(items,%s);
 unsigned long long lower=n>2000?n-2000:0;
 for(unsigned long long i=n;i>lower && !found;i--){
  void *item=((void*(*)(void*,void*,unsigned long long))objc_msgSend)(items,%s,i-1);
  if(!item || !(%s))continue;
  void *m=%s;
  if(!m || !(%s) || %s)continue;
  for(int k=0;k<2 && !found;k++){
   void *s=0;
   if(k==0 && %s)s=%s;
   if(k==1 && %s){void *a=%s;if(a && %s)s=%s;}
   if(s && %s && %s)found=(unsigned long long)%s;
  }
 }
}
found;})''' % (RESOLVE, sel('count'), sel('objectAtIndex:'), has('item', 'message'), obj('item', 'message'),
               has('m', 'amISender'), boolean('m', 'amISender'), has('m', 'text'), obj('m', 'text'),
               has('m', 'attrText'), obj('m', 'attrText'), has('a', 'string'), obj('a', 'string'),
               contains('s', begin), contains('s', end), obj('s', 'UTF8String'))
