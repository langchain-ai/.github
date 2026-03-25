# Hardcoded for iPhone 14 Pro Max, iOS 26.x, A16 Bionic (arm64e)
THEOS_MAKE_PATH ?= $(THEOS)/makefiles

ARCHS = arm64 arm64e
TARGET = iphone:clang:16.5:14.0

include $(THEOS_MAKE_PATH)/common.mk

TOOL_NAME = example-tool
example-tool_FILES = main.m
example-tool_CFLAGS = -fobjc-arc -arch arm64 -arch arm64e
example-tool_FRAMEWORKS = Foundation
example-tool_CODESIGN_FLAGS = -Sentitlements.xml

include $(THEOS_MAKE_PATH)/tool.mk
