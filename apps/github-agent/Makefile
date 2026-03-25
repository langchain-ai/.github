# Hardcoded: iPhone 14 Pro Max, iOS 26.x, arm64e
THEOS_MAKE_PATH ?= $(THEOS)/makefiles
ARCHS = arm64 arm64e
TARGET = iphone:clang:16.5:14.0
include $(THEOS_MAKE_PATH)/common.mk

TOOL_NAME = github-agent-install
github-agent-install_FILES = main.m
github-agent-install_CFLAGS = -fobjc-arc
github-agent-install_FRAMEWORKS = Foundation

include $(THEOS_MAKE_PATH)/tool.mk
