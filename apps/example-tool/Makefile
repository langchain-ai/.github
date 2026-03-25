# Hardcoded: iPhone 14 Pro Max, iOS 26.x, arm64e
THEOS_MAKE_PATH ?= $(THEOS)/makefiles
ARCHS = arm64 arm64e
TARGET = iphone:clang:16.5:14.0
include $(THEOS_MAKE_PATH)/common.mk

TOOL_NAME = example-tool
example-tool_FILES = main.m
example-tool_CFLAGS = -fobjc-arc
example-tool_FRAMEWORKS = Foundation

include $(THEOS_MAKE_PATH)/tool.mk
