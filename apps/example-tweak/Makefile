# Hardcoded for iPhone 14 Pro Max, iOS 26.x, A16 Bionic (arm64e)
THEOS_MAKE_PATH ?= $(THEOS)/makefiles

ARCHS = arm64 arm64e
TARGET = iphone:clang:16.5:14.0

include $(THEOS_MAKE_PATH)/common.mk

TWEAK_NAME = ExampleTweak
ExampleTweak_FILES = Tweak.x
ExampleTweak_CFLAGS = -fobjc-arc -arch arm64 -arch arm64e
ExampleTweak_FRAMEWORKS = UIKit Foundation
ExampleTweak_LIBRARIES = substrate

include $(THEOS_MAKE_PATH)/tweak.mk
