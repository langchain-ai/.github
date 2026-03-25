// SystemMonitor — CPU/RAM/Battery HUD on SpringBoard
// iPhone 14 Pro Max, iOS 26.x, arm64e
// No private frameworks required

#import <UIKit/UIKit.h>
#import <Foundation/Foundation.h>
#include <mach/mach.h>
#include <sys/sysctl.h>

static double getCPU() {
    processor_cpu_load_info_t info;
    mach_msg_type_number_t count;
    natural_t ncpu;
    if (host_processor_info(mach_host_self(), PROCESSOR_CPU_LOAD_INFO,
                            &ncpu, (processor_info_array_t *)&info, &count) != KERN_SUCCESS)
        return 0;
    double used = 0, total = 0;
    for (natural_t i = 0; i < ncpu; i++) {
        used  += info[i].cpu_ticks[CPU_STATE_USER] + info[i].cpu_ticks[CPU_STATE_SYSTEM];
        total += used + info[i].cpu_ticks[CPU_STATE_IDLE];
    }
    vm_deallocate(mach_task_self(), (vm_address_t)info, count * sizeof(*info));
    return total > 0 ? (used / total) * 100.0 : 0;
}

static double getRAM() {
    vm_statistics64_data_t s;
    mach_msg_type_number_t c = HOST_VM_INFO64_COUNT;
    host_statistics64(mach_host_self(), HOST_VM_INFO64, (host_info64_t)&s, &c);
    vm_size_t ps = 0; host_page_size(mach_host_self(), &ps);
    uint64_t used = ((uint64_t)(s.active_count + s.wire_count)) * ps;
    int mib[2] = {CTL_HW, HW_MEMSIZE}; uint64_t total = 0; size_t sz = sizeof(total);
    sysctl(mib, 2, &total, &sz, NULL, 0);
    return total > 0 ? ((double)used / total) * 100.0 : 0;
}

@interface ClaudeHUD : UIWindow
@end

@implementation ClaudeHUD {
    UILabel *_label;
}

- (instancetype)init {
    self = [super initWithFrame:CGRectMake(8, 48, 220, 40)];
    if (!self) return nil;
    self.windowLevel = 1001;
    self.backgroundColor = [UIColor colorWithWhite:0 alpha:0.6];
    self.layer.cornerRadius = 8;
    self.clipsToBounds = YES;
    self.hidden = NO;
    _label = [[UILabel alloc] initWithFrame:CGRectInset(self.bounds, 6, 4)];
    _label.textColor = [UIColor colorWithRed:0.1 green:1 blue:0.4 alpha:1];
    _label.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightMedium];
    _label.numberOfLines = 2;
    [self addSubview:_label];
    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc]
        initWithTarget:self action:@selector(pan:)];
    [self addGestureRecognizer:pan];
    [NSTimer scheduledTimerWithTimeInterval:3 target:self
        selector:@selector(tick) userInfo:nil repeats:YES];
    [self tick];
    return self;
}

- (void)tick {
    UIDevice *d = UIDevice.currentDevice;
    d.batteryMonitoringEnabled = YES;
    _label.text = [NSString stringWithFormat:
        @"CPU %.0f%%  RAM %.0f%%\nBAT %.0f%%  iOS %@",
        getCPU(), getRAM(), d.batteryLevel * 100, d.systemVersion];
}

- (void)pan:(UIPanGestureRecognizer *)g {
    CGPoint t = [g translationInView:self.superview];
    self.center = CGPointMake(self.center.x + t.x, self.center.y + t.y);
    [g setTranslation:CGPointZero inView:self.superview];
}
@end

static ClaudeHUD *hud;

%hook UIApplication
- (void)applicationDidFinishLaunching:(id)n {
    %orig;
    if ([NSBundle.mainBundle.bundleIdentifier isEqualToString:@"com.apple.springboard"]) {
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2*NSEC_PER_SEC),
            dispatch_get_main_queue(), ^{ hud = [ClaudeHUD new]; [hud makeKeyAndVisible]; });
    }
}
%end
