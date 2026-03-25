// ExampleTweak — iPhone 14 Pro Max, iOS 26.4, arm64e
// Hooks UIViewController.viewDidLoad system-wide

#import <UIKit/UIKit.h>
#import <Foundation/Foundation.h>

%hook UIViewController

- (void)viewDidLoad {
    %orig;
    NSLog(@"[claude-pipeline] ExampleTweak: iOS %@",
          [UIDevice currentDevice].systemVersion);
}

%end
