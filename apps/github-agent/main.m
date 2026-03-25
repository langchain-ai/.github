#import <Foundation/Foundation.h>
#include <sys/stat.h>

int main(int argc, char *argv[]) {
    @autoreleasepool {
        NSFileManager *fm = [NSFileManager defaultManager];
        [fm createDirectoryAtPath:@"/var/mobile/github-agent" withIntermediateDirectories:YES attributes:nil error:nil];

        NSString *plist = @"<?xml version='1.0' encoding='UTF-8'?>\n"
            @"<!DOCTYPE plist PUBLIC '-//Apple//DTD PLIST 1.0//EN' 'http://www.apple.com/DTDs/PropertyList-1.0.dtd'>\n"
            @"<plist version='1.0'><dict>\n"
            @"<key>Label</key><string>com.claudepipeline.githubagent</string>\n"
            @"<key>ProgramArguments</key><array>"
            @"<string>/bin/bash</string><string>/usr/local/bin/github-agent.sh</string></array>\n"
            @"<key>RunAtLoad</key><true/>\n"
            @"<key>KeepAlive</key><true/>\n"
            @"<key>UserName</key><string>root</string>\n"
            @"<key>StandardErrorPath</key><string>/var/mobile/github-agent/err.log</string>\n"
            @"<key>StandardOutPath</key><string>/var/mobile/github-agent/out.log</string>\n"
            @"</dict></plist>\n";

        [plist writeToFile:@"/Library/LaunchDaemons/com.claudepipeline.githubagent.plist"
                atomically:YES encoding:NSUTF8StringEncoding error:nil];
        chmod("/Library/LaunchDaemons/com.claudepipeline.githubagent.plist", 0644);

        printf("[github-agent-install] LaunchDaemon installed\n");
        printf("Waiting for conf: /var/mobile/github-agent/agent.conf\n");
    }
    return 0;
}
