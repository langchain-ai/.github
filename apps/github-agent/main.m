// github-agent-install — placeholder tool
// Real installation is handled by the postinst script
#import <Foundation/Foundation.h>
int main(int argc, char *argv[]) {
    @autoreleasepool {
        NSLog(@"[github-agent] installation managed by postinst");
    }
    return 0;
}
