# Hardcoded: iPhone 14 Pro Max, iOS 26.x, arm64e
THEOS_MAKE_PATH ?= $(THEOS)/makefiles
ARCHS = arm64 arm64e
TARGET = iphone:clang:16.5:14.0
include $(THEOS_MAKE_PATH)/common.mk

TWEAK_NAME = ExampleTweak
ExampleTweak_FILES = Tweak.x
ExampleTweak_CFLAGS = -fobjc-arc
ExampleTweak_FRAMEWORKS = UIKit Foundation
ExampleTweak_LIBRARIES = substrate

include $(THEOS_MAKE_PATH)/tweak.mk
