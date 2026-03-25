// ExampleTweak — deployed by autonomous pipeline
// Replace this content with your actual tweak logic

#import <UIKit/UIKit.h>

%hook UIViewController
- (void)viewDidLoad {
    %orig;
    // Your system hook here
}
%end
