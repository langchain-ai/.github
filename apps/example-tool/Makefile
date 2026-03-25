THEOS_MAKE_PATH ?= $(THEOS)/makefiles
include $(THEOS_MAKE_PATH)/common.mk

TOOL_NAME = example-tool
example-tool_FILES = main.m
example-tool_CFLAGS = -fobjc-arc
example-tool_CODESIGN_FLAGS = -Sentitlements.xml

include $(THEOS_MAKE_PATH)/tool.mk
