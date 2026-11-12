#import <Foundation/Foundation.h>
@interface FixtureMessage:NSObject
@property(nonatomic,strong) NSString *text;
@property(nonatomic) BOOL amISender;
@end
@implementation FixtureMessage @end
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
__attribute__((noinline)) void fixture_ready(void){__asm__ volatile("");}
int main(void){@autoreleasepool {
 shared=[WEWWeClawChatMainViewController new];shared.currentConversationContextId=@"fixture-session";
 FixtureList *list=[FixtureList new];list.dataArray=[NSMutableArray array];
 for(NSNumber *sent in @[@YES,@NO]){
  FixtureMessage *message=[FixtureMessage new];message.amISender=sent.boolValue;
  message.text=sent.boolValue?@"BEGIN_outgoing outgoing must be ignored END_outgoing":@"preamble\nBEGIN_fixture\n| Field | Value |\n| a | b |\nEND_fixture\nsuffix";
  FixtureItem *item=[FixtureItem new];item.message=message;[list.dataArray addObject:item];
 }
 FixtureInput *input=[FixtureInput new];input.list=list;
 FixtureView *view=[FixtureView new];view.inputVC=input;
 FixtureChat *chat=[FixtureChat new];chat.clawView=view;chat.msgListCtrl=list;shared.currentChatViewController=chat;
 fixture_ready();
 }return 0;}
