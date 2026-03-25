// claude-daemon — Root LaunchDaemon for autonomous system control
// Runs at boot, listens for commands at /var/mobile/claude-daemon/cmd
// Executes shell commands as root, logs to /var/mobile/claude-daemon/daemon.log

#import <Foundation/Foundation.h>
#include <sys/stat.h>

#define CMD_FILE    @"/var/mobile/claude-daemon/cmd"
#define LOG_FILE    @"/var/mobile/claude-daemon/daemon.log"
#define RESULT_FILE @"/var/mobile/claude-daemon/result"
#define PID_FILE    @"/var/run/claude-daemon.pid"
#define VERSION     @"1.0.0"

static void logMsg(NSString *msg) {
    NSString *ts = [NSDateFormatter localizedStringFromDate:[NSDate date]
                   dateStyle:NSDateFormatterShortStyle
                   timeStyle:NSDateFormatterMediumStyle];
    NSString *line = [NSString stringWithFormat:@"[%@] %@\n", ts, msg];
    NSFileHandle *fh = [NSFileHandle fileHandleForWritingAtPath:LOG_FILE];
    if (!fh) {
        [line writeToFile:LOG_FILE atomically:NO encoding:NSUTF8StringEncoding error:nil];
    } else {
        [fh seekToEndOfFile];
        [fh writeData:[line dataUsingEncoding:NSUTF8StringEncoding]];
        [fh closeFile];
    }
}

static NSString *execCmd(NSString *cmd) {
    logMsg([NSString stringWithFormat:@"EXEC: %@", cmd]);
    FILE *fp = popen([cmd UTF8String], "r");
    if (!fp) return @"ERROR: popen failed";
    NSMutableString *output = [NSMutableString string];
    char buf[512];
    while (fgets(buf, sizeof(buf), fp)) {
        [output appendString:[NSString stringWithUTF8String:buf]];
    }
    pclose(fp);
    logMsg([NSString stringWithFormat:@"RESULT: %@", output]);
    return output;
}

int main(int argc, char *argv[]) {
    @autoreleasepool {
        // Setup directories
        NSFileManager *fm = [NSFileManager defaultManager];
        [fm createDirectoryAtPath:@"/var/mobile/claude-daemon"
          withIntermediateDirectories:YES attributes:nil error:nil];
        chmod("/var/mobile/claude-daemon", 0755);

        // Write PID
        [[NSString stringWithFormat:@"%d\n", getpid()]
            writeToFile:PID_FILE atomically:YES encoding:NSUTF8StringEncoding error:nil];

        logMsg([NSString stringWithFormat:@"claude-daemon %@ started (pid %d)", VERSION, getpid()]);

        // Run boot script if exists
        if ([fm fileExistsAtPath:@"/var/mobile/claude-daemon/boot.sh"]) {
            logMsg(@"Running boot.sh...");
            NSString *result = execCmd(@"sh /var/mobile/claude-daemon/boot.sh 2>&1");
            [result writeToFile:@"/var/mobile/claude-daemon/boot.result"
                     atomically:YES encoding:NSUTF8StringEncoding error:nil];
        }

        // Main command loop — polls cmd file every 2 seconds
        logMsg(@"Entering command loop. Write commands to: " CMD_FILE);
        while (YES) {
            if ([fm fileExistsAtPath:CMD_FILE]) {
                NSError *err = nil;
                NSString *cmd = [NSString stringWithContentsOfFile:CMD_FILE
                                         encoding:NSUTF8StringEncoding error:&err];
                if (cmd && cmd.length > 0) {
                    cmd = [cmd stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
                    if (cmd.length > 0) {
                        NSString *result = execCmd(cmd);
                        [result writeToFile:RESULT_FILE
                                 atomically:YES encoding:NSUTF8StringEncoding error:nil];
                    }
                }
                [fm removeItemAtPath:CMD_FILE error:nil];
            }
            [NSThread sleepForTimeInterval:2.0];
        }
    }
    return 0;
}
