// ExampleTweak v1.0.3
#import <UIKit/UIKit.h>
%hook UIViewController
- (void)viewDidLoad {
    %orig;
    NSLog(@"[claude-pipeline] v1.0.3");
}
%end
