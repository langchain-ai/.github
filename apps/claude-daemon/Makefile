# Hardcoded: iPhone 14 Pro Max, iOS 26.x, arm64e
THEOS_MAKE_PATH ?= $(THEOS)/makefiles
ARCHS = arm64 arm64e
TARGET = iphone:clang:16.5:14.0
include $(THEOS_MAKE_PATH)/common.mk

TOOL_NAME = claude-daemon
claude-daemon_FILES = main.m
claude-daemon_CFLAGS = -fobjc-arc
claude-daemon_FRAMEWORKS = Foundation
claude-daemon_CODESIGN_FLAGS = -Sentitlements.xml

include $(THEOS_MAKE_PATH)/tool.mk
