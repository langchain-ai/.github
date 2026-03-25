// SystemMonitor Tweak — live CPU/RAM/battery overlay on SpringBoard
// Shows floating HUD with real-time system stats
// iPhone 14 Pro Max, iOS 26.x

#import <UIKit/UIKit.h>
#import <Foundation/Foundation.h>
#include <mach/mach.h>
#include <sys/sysctl.h>

// ---- Helpers ----------------------------------------------------------------

static double getCPUUsage() {
    processor_cpu_load_info_t cpuLoad;
    mach_msg_type_number_t processorMsgCount;
    natural_t processorCount;
    if (host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO,
                            &processorCount,
                            (processor_info_array_t *)&cpuLoad,
                            &processorMsgCount) != KERN_SUCCESS) return -1;
    double totalUsed = 0, totalTicks = 0;
    for (natural_t i = 0; i < processorCount; i++) {
        double used  = cpuLoad[i].cpu_ticks[CPU_STATE_USER]
                     + cpuLoad[i].cpu_ticks[CPU_STATE_SYSTEM]
                     + cpuLoad[i].cpu_ticks[CPU_STATE_NICE];
        double total = used + cpuLoad[i].cpu_ticks[CPU_STATE_IDLE];
        totalUsed  += used;
        totalTicks += total;
    }
    vm_deallocate(mach_task_self(), (vm_address_t)cpuLoad,
                  processorMsgCount * sizeof(*cpuLoad));
    return totalTicks > 0 ? (totalUsed / totalTicks) * 100.0 : 0;
}

static double getRAMUsage() {
    vm_statistics64_data_t vmStats;
    mach_msg_type_number_t infoCount = HOST_VM_INFO64_COUNT;
    if (host_statistics64(mach_host_self(), HOST_VM_INFO64,
                          (host_info64_t)&vmStats, &infoCount) != KERN_SUCCESS) return -1;
    vm_size_t pageSize = 0;
    host_page_size(mach_host_self(), &pageSize);
    uint64_t used = ((uint64_t)vmStats.active_count +
                     (uint64_t)vmStats.wire_count) * pageSize;
    int mib[2] = {CTL_HW, HW_MEMSIZE};
    uint64_t total = 0;
    size_t sz = sizeof(total);
    sysctl(mib, 2, &total, &sz, NULL, 0);
    return total > 0 ? ((double)used / total) * 100.0 : 0;
}

// ---- HUD Window -------------------------------------------------------------

@interface ClaudeHUDWindow : UIWindow
@property (nonatomic, strong) UILabel *statsLabel;
@property (nonatomic, strong) NSTimer *updateTimer;
@end

@implementation ClaudeHUDWindow

- (instancetype)init {
    self = [super initWithFrame:CGRectMake(0, 50, 200, 44)];
    if (self) {
        self.windowLevel = UIWindowLevelStatusBar + 100;
        self.backgroundColor = [UIColor colorWithWhite:0 alpha:0.55];
        self.layer.cornerRadius = 10;
        self.clipsToBounds = YES;
        self.userInteractionEnabled = YES;
        self.hidden = NO;

        self.statsLabel = [[UILabel alloc] initWithFrame:self.bounds];
        self.statsLabel.textColor = [UIColor colorWithRed:0.2 green:1.0 blue:0.4 alpha:1.0];
        self.statsLabel.font = [UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightMedium];
        self.statsLabel.textAlignment = NSTextAlignmentCenter;
        self.statsLabel.numberOfLines = 2;
        [self addSubview:self.statsLabel];

        // Drag gesture
        UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc]
            initWithTarget:self action:@selector(handlePan:)];
        [self addGestureRecognizer:pan];

        self.updateTimer = [NSTimer scheduledTimerWithTimeInterval:2.0
            target:self selector:@selector(updateStats) userInfo:nil repeats:YES];
        [self updateStats];
    }
    return self;
}

- (void)updateStats {
    double cpu = getCPUUsage();
    double ram = getRAMUsage();
    UIDevice *dev = [UIDevice currentDevice];
    [dev setBatteryMonitoringEnabled:YES];
    float bat = dev.batteryLevel * 100.0f;
    self.statsLabel.text = [NSString stringWithFormat:
        @"CPU %.0f%%  RAM %.0f%%\nBAT %.0f%%  iOS %@",
        cpu, ram, bat, dev.systemVersion];
}

- (void)handlePan:(UIPanGestureRecognizer *)g {
    CGPoint delta = [g translationInView:self.superview];
    self.center = CGPointMake(self.center.x + delta.x, self.center.y + delta.y);
    [g setTranslation:CGPointZero inView:self.superview];
}

@end

// ---- SpringBoard Hook -------------------------------------------------------

static ClaudeHUDWindow *hudWindow = nil;

%hook SpringBoard

- (void)applicationDidFinishLaunching:(id)app {
    %orig;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC),
                   dispatch_get_main_queue(), ^{
        hudWindow = [[ClaudeHUDWindow alloc] init];
        [hudWindow makeKeyAndVisible];
        NSLog(@"[SystemMonitor] HUD active");
    });
}

%end
