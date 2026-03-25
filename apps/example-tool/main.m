// example-tool — standalone CLI tool deployed to jailbroken device
#import <Foundation/Foundation.h>

int main(int argc, char *argv[]) {
    @autoreleasepool {
        NSLog(@"[claude-ios] example-tool running on %@", [[UIDevice currentDevice] systemVersion]);
        printf("Hello from autonomous pipeline\n");
    }
    return 0;
}
