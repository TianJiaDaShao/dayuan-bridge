"""Fixed Objective-C operations. No cached pointers or injected shell commands."""
import json


def literal(value):
    # UTF-8 literals preserve non-BMP characters (JSON surrogate escapes are
    # invalid universal character names in Clang's Objective-C parser).
    return '((void*(*)(void*,void*,const char*))objc_msgSend)(((void*(*)(const char*))objc_getClass)("NSString"),((void*(*)(const char*))sel_registerName)("stringWithUTF8String:"),%s)' % json.dumps(value, ensure_ascii=False)


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
HEADLESS_KEY = 'dayuan.bridge.headless.v2'
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
    code+='void *v=0,*chat=0;'
    for target,source,selector in [('v','main','view'),('chat','main','currentChatViewController')]:
        code+='if(%s && %s)%s=%s;' % (source,has(source,selector),target,obj(source,selector))
    code+='void *right=main?%s:0;void *create=0;void *flag=%s;' % (obj('main','rightVC'),sel('dayuan.bridge.session_creation_requested'))
    code+='if(right && !chat && %s){%s;create=%s;}' % (has('right','wew_ensureCreateView'),obj('right','wew_ensureCreateView'),obj('right','createView'))
    code+='void *requested=main?((void*(*)(void*,void*))objc_getAssociatedObject)(main,flag):0;'
    code+='if(requested && %s && ((double(*)(void*,void*))objc_msgSend)(requested,%s)<-120.0){requested=0;}' % (has('requested','timeIntervalSinceNow'),sel('timeIntervalSinceNow'))
    code+='if(create && !chat && !requested && %s){((void(*)(void*,void*,void*,unsigned long))objc_setAssociatedObject)(main,flag,(void*)%s,1);((void(*)(void*,void*,void*))objc_msgSend)(create,%s,(void*)%s);}' % (has('create','wew_setInputTextAndSend:'),obj('((void*(*)(const char*))objc_getClass)("NSDate")','date'),sel('wew_setInputTextAndSend:'),literal('圆桥连接初始化。只回复“已就绪”，不要执行其他操作。'))
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


def bootstrap_ready_expression():
    code=RESOLVE+'void *flagkey=%s;void *ready=main?((void*(*)(void*,void*))objc_getAssociatedObject)(main,flagkey):0;' % sel('dayuan.bridge.bootstrap_complete')
    code+='if(main && !ready && %s){ready=%s;((void(*)(void*,void*,void*,unsigned long))objc_setAssociatedObject)(main,flagkey,ready,1);}' % (result_expression('已就绪','已就绪'),obj('((void*(*)(const char*))objc_getClass)("NSNull")','null'))
    return '({'+code+'(unsigned long long)(ready?1:0);})'


def _number_bool(value):
    return '((void*(*)(void*,void*,unsigned char))objc_msgSend)(((void*(*)(const char*))objc_getClass)("NSNumber"),%s,(unsigned char)(%s))' % (sel('numberWithBool:'),value)


def _json_snapshot(code, fields):
    code+='void *dybridge_dict=%s;' % obj('((void*(*)(const char*))objc_getClass)("NSMutableDictionary")','dictionary')
    for name,value in fields:
        code+='{void *dybridge_value=%s;if(dybridge_value)((void(*)(void*,void*,void*,void*))objc_msgSend)(dybridge_dict,%s,dybridge_value,(void*)%s);}' % (value,sel('setObject:forKey:'),literal(name))
    code+='void *dybridge_data=((void*(*)(void*,void*,void*,unsigned long,void*))objc_msgSend)(((void*(*)(const char*))objc_getClass)("NSJSONSerialization"),%s,dybridge_dict,0,(void*)0);' % sel('dataWithJSONObject:options:error:')
    code+='void *dybridge_json=%s;dybridge_json=((void*(*)(void*,void*,void*,unsigned long))objc_msgSend)(dybridge_json,%s,dybridge_data,4);dybridge_json=%s;(unsigned long long)%s;' % (obj('((void*(*)(const char*))objc_getClass)("NSString")','alloc'),sel('initWithData:encoding:'),obj('dybridge_json','autorelease'),obj('dybridge_json','UTF8String'))
    return '({'+code+'})'


def last_message_key_expression(outgoing_only=False):
    code=RESOLVE+'void *dybridge_key=0;unsigned long long dybridge_count=items?(unsigned long long)%s:0;' % obj('items','count')
    code+='for(unsigned long long dybridge_i=dybridge_count;dybridge_i>0 && !dybridge_key;dybridge_i--){void *dybridge_item=((void*(*)(void*,void*,unsigned long long))objc_msgSend)(items,%s,dybridge_i-1);if(!dybridge_item || !(%s))continue;void *dybridge_msg=%s;' % (sel('objectAtIndex:'),has('dybridge_item','message'),obj('dybridge_item','message'))
    if outgoing_only:
        code+='if(!dybridge_msg || !(%s) || !(%s))continue;' % (has('dybridge_msg','amISender'),boolean('dybridge_msg','amISender'))
    code+='if(dybridge_msg && %s)dybridge_key=%s;}(unsigned long long)(dybridge_key?%s:0);' % (has('dybridge_msg','msgKey'),obj('dybridge_msg','msgKey'),obj('dybridge_key','UTF8String'))
    return '({'+code+'})'


def reply_snapshot_expression(begin,end,sent_key=None,baseline_key=None):
    # The outgoing rich message may have neither text nor attrText. Its stable
    # msgKey and the pre-dispatch baseline are the primary task association.
    # Exact envelope markers remain a backward-compatible recovery anchor.
    code=RESOLVE+"""
void *dybridge_reply=0,*dybridge_reply_text=0,*dybridge_outkey=0,*dybridge_legacy=0,*dybridge_legacy_text=0;
unsigned char dybridge_active=0,dybridge_after_baseline=0,dybridge_legacy_done=0;
unsigned long long dybridge_count=items?(unsigned long long)COUNT:0;
for(unsigned long long dybridge_i=dybridge_count>2000?dybridge_count-2000:0;dybridge_i<dybridge_count;dybridge_i++){
 void *dybridge_item=((void*(*)(void*,void*,unsigned long long))objc_msgSend)(items,INDEX,dybridge_i);
 if(!dybridge_item || !(HAS_MSG))continue;
 void *dybridge_msg=GET_MSG;if(!dybridge_msg || !(HAS_SENDER))continue;
 void *dybridge_text=0,*dybridge_key=0,*dybridge_model=0;
 if(HAS_TEXT)dybridge_text=GET_TEXT;
 if(!dybridge_text || !(unsigned long long)TEXT_LENGTH){if(HAS_ATTR){void *dybridge_attr=GET_ATTR;if(dybridge_attr && HAS_STRING)dybridge_text=GET_STRING;}}
 if(HAS_KEY)dybridge_key=GET_KEY;
 unsigned char dybridge_is_sender=IS_SENDER;
 unsigned char dybridge_begin=dybridge_text && MATCH_BEGIN,dybridge_end=dybridge_text && MATCH_END;
 unsigned char dybridge_key_match=KEY_MATCH,dybridge_is_baseline=BASELINE_MATCH;
 if(dybridge_is_sender){
  if(dybridge_key_match || (dybridge_after_baseline && !dybridge_active)){
   dybridge_active=1;dybridge_outkey=dybridge_key;dybridge_reply=0;dybridge_reply_text=0;
  }else if(dybridge_active){break;}
 }else{
  if(HAS_MODEL)dybridge_model=GET_MODEL;
  unsigned char dybridge_known=dybridge_model && HAS_FINISH;
  unsigned char dybridge_finished=dybridge_known && IS_FINISHED;
  if(dybridge_active){dybridge_reply=dybridge_msg;dybridge_reply_text=dybridge_text;}
  if(dybridge_text && ((dybridge_known && dybridge_finished && (dybridge_begin || dybridge_end)) || (!dybridge_known && dybridge_begin && dybridge_end))){dybridge_legacy=dybridge_msg;dybridge_legacy_text=dybridge_text;dybridge_legacy_done=1;}
 }
 if(dybridge_is_baseline)dybridge_after_baseline=1;
}
void *dybridge_result=0,*dybridge_match=0;unsigned char dybridge_complete=0,dybridge_known=0;
if(dybridge_reply){void *dybridge_model=0;if(REPLY_HAS_MODEL)dybridge_model=REPLY_GET_MODEL;dybridge_known=dybridge_model && HAS_FINISH;
 if(dybridge_known && IS_FINISHED && dybridge_reply_text && (unsigned long long)REPLY_LENGTH){dybridge_result=dybridge_reply_text;dybridge_complete=1;dybridge_match=MATCH_NATIVE;}
}
if(!dybridge_complete && dybridge_legacy_done && !dybridge_known && (!dybridge_active || dybridge_legacy==dybridge_reply)){dybridge_result=dybridge_legacy_text;dybridge_complete=1;dybridge_match=MATCH_ENVELOPE;}
"""
    replacements={'COUNT':obj('items','count'),'INDEX':sel('objectAtIndex:'),'HAS_MSG':has('dybridge_item','message'),'GET_MSG':obj('dybridge_item','message'),'HAS_SENDER':has('dybridge_msg','amISender'),'HAS_TEXT':has('dybridge_msg','text'),'GET_TEXT':obj('dybridge_msg','text'),'TEXT_LENGTH':obj('dybridge_text','length'),'HAS_ATTR':has('dybridge_msg','attrText'),'GET_ATTR':obj('dybridge_msg','attrText'),'HAS_STRING':has('dybridge_attr','string'),'GET_STRING':obj('dybridge_attr','string'),'HAS_KEY':has('dybridge_msg','msgKey'),'GET_KEY':obj('dybridge_msg','msgKey'),'IS_SENDER':boolean('dybridge_msg','amISender'),'MATCH_BEGIN':contains('dybridge_text',begin),'MATCH_END':contains('dybridge_text',end),'HAS_MODEL':has('dybridge_msg','agentFlushModel'),'GET_MODEL':obj('dybridge_msg','agentFlushModel'),'HAS_FINISH':has('dybridge_model','isStreamFinished'),'IS_FINISHED':boolean('dybridge_model','isStreamFinished'),'REPLY_HAS_MODEL':has('dybridge_reply','agentFlushModel'),'REPLY_GET_MODEL':obj('dybridge_reply','agentFlushModel'),'REPLY_LENGTH':obj('dybridge_reply_text','length'),'MATCH_NATIVE':literal('native_completion'),'MATCH_ENVELOPE':literal('envelope_recovery')}
    replacements['KEY_MATCH']='dybridge_key && '+contains('dybridge_key',sent_key) if sent_key else '0'
    replacements['BASELINE_MATCH']='dybridge_key && '+contains('dybridge_key',baseline_key) if baseline_key else '0'
    # Key equality must be exact, never substring matching.
    for field,value in [('KEY_MATCH',sent_key),('BASELINE_MATCH',baseline_key)]:
        if value:replacements[field]='dybridge_key && ((unsigned char(*)(void*,void*,void*))objc_msgSend)(dybridge_key,%s,(void*)%s)' % (sel('isEqualToString:'),literal(value))
    import re
    code=re.sub(r'\b('+'|'.join(sorted(replacements,key=len,reverse=True))+r')\b',lambda m:replacements[m.group(0)],code)
    return _json_snapshot(code,[('ready',_number_bool('dybridge_complete')),('completion_known',_number_bool('dybridge_known')),('outgoing_found',_number_bool('dybridge_active')),('sent_message_key','dybridge_outkey'),('text','dybridge_result'),('match','dybridge_match')])
