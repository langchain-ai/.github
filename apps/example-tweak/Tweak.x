// ExampleTweak v1.0.2 — pipeline retry with fixed workflow
// Target: iPhone 14 Pro Max, iOS 26.4, arm64e

#import <UIKit/UIKit.h>

%hook UIViewController
- (void)viewDidLoad {
    %orig;
    NSLog(@"[claude-pipeline] v1.0.2 live on iOS %@",
          [[UIDevice currentDevice] systemVersion]);
}
%end
