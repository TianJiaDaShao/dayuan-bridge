#import <Foundation/Foundation.h>
@interface FixtureFlushModel:NSObject
@property(nonatomic) BOOL isStreamFinished;
@end
@implementation FixtureFlushModel @end
@interface FixtureMessage:NSObject
@property(nonatomic,strong) NSString *text;
@property(nonatomic) BOOL amISender;
@property(nonatomic,strong) NSString *msgKey;
@property(nonatomic,strong) FixtureFlushModel *agentFlushModel;
@end
@implementation FixtureMessage
-(id)init{self=[super init];if(self)self.msgKey=[NSUUID UUID].UUIDString;return self;}
@end
@interface FixtureItem:NSObject
@property(nonatomic,strong) FixtureMessage *message;
@end
@implementation FixtureItem @end
@interface FixtureList:NSObject
@property(nonatomic,strong) NSMutableArray *dataArray;
@end
@implementation FixtureList @end
@interface FixtureInput:NSObject
@property(nonatomic,strong) FixtureList *list;
-(void)wew_sendBypassTextStorageWithText:(NSString*)text subjectEntry:(id)entry;
@end
@implementation FixtureInput
-(void)wew_sendBypassTextStorageWithText:(NSString*)text subjectEntry:(id)entry {
 FixtureMessage *message=[FixtureMessage new];message.text=text;message.amISender=YES;
 FixtureItem *item=[FixtureItem new];item.message=message;[self.list.dataArray addObject:item];
}
@end
@interface FixtureView:NSObject
@property(nonatomic,strong) FixtureInput *inputVC;
@end
@implementation FixtureView @end
@interface FixtureChat:NSObject
@property(nonatomic,strong) FixtureView *clawView;
@property(nonatomic,strong) FixtureList *msgListCtrl;
@end
@implementation FixtureChat @end
@interface WEWWeClawChatMainViewController:NSObject
@property(nonatomic,strong) FixtureChat *currentChatViewController;
@property(nonatomic,strong) NSString *currentConversationContextId;
+(id)existingInstance;
@end
static WEWWeClawChatMainViewController *shared;
@implementation WEWWeClawChatMainViewController
+(id)existingInstance{return shared;}
@end
static void appendFixture(FixtureList *list,BOOL sent,NSString *text,NSString *key,int finished){
 FixtureMessage *m=[FixtureMessage new];m.text=text;m.amISender=sent;m.msgKey=key;
 if(finished>=0){m.agentFlushModel=[FixtureFlushModel new];m.agentFlushModel.isStreamFinished=finished;}
 FixtureItem *item=[FixtureItem new];item.message=m;[list.dataArray addObject:item];
}
__attribute__((noinline)) void fixture_ready(void){__asm__ volatile("");}
int main(void){@autoreleasepool {
 shared=[WEWWeClawChatMainViewController new];shared.currentConversationContextId=@"fixture-session";
 FixtureList *list=[FixtureList new];list.dataArray=[NSMutableArray array];
 for(NSNumber *sent in @[@YES,@NO]){
  FixtureMessage *message=[FixtureMessage new];message.amISender=sent.boolValue;
  message.text=sent.boolValue?@"BEGIN_outgoing outgoing must be ignored END_outgoing":@"preamble\nBEGIN_fixture\n| Field | Value |\n| a | b |\nEND_fixture\nsuffix";
  FixtureItem *item=[FixtureItem new];item.message=message;[list.dataArray addObject:item];
 }
 appendFixture(list,NO,@"baseline",@"baseline-native",1);
 appendFixture(list,YES,@"",@"sent-native",-1);
 appendFixture(list,NO,@"完整答复\n| 字段 | 内容 |",@"reply-native",1);
 appendFixture(list,YES,@"",@"sent-stream",-1);
 appendFixture(list,NO,@"still streaming",@"reply-stream",0);
 appendFixture(list,YES,@"",@"sent-multi",-1);
 appendFixture(list,NO,@"finished progress",@"reply-progress",1);
 appendFixture(list,NO,@"unfinished final",@"reply-unfinished",0);
 appendFixture(list,YES,@"",@"sent-other",-1);
 appendFixture(list,NO,@"other answer",@"reply-other",1);
 appendFixture(list,NO,@"只有尾标记的答复\nEND_single",@"reply-single",1);
 appendFixture(list,NO,@"BEGIN_pending not done END_pending",@"reply-pending",0);
 FixtureInput *input=[FixtureInput new];input.list=list;
 FixtureView *view=[FixtureView new];view.inputVC=input;
 FixtureChat *chat=[FixtureChat new];chat.clawView=view;chat.msgListCtrl=list;shared.currentChatViewController=chat;
 fixture_ready();
 }return 0;}
