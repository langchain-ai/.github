// ExampleTweak v1.0.1 — first live deploy via autonomous pipeline
// Target: iPhone 14 Pro Max, iOS 26.4, arm64e

#import <UIKit/UIKit.h>

%hook UIViewController
- (void)viewDidLoad {
    %orig;
    NSLog(@"[claude-pipeline] deployed successfully on iOS %@",
          [[UIDevice currentDevice] systemVersion]);
}
%end
