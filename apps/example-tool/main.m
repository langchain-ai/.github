// example-tool — bare CLI tool, no UIKit
// Foundation only — safe for tool target

#import <Foundation/Foundation.h>

int main(int argc, char *argv[]) {
    @autoreleasepool {
        printf("[claude-pipeline] example-tool v1.0 running\n");
        NSLog(@"[claude-pipeline] tool deployed via autonomous pipeline");

        if (argc > 1) {
            NSLog(@"[claude-pipeline] arg: %s", argv[1]);
        }
    }
    return 0;
}
