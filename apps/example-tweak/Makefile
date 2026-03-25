THEOS_MAKE_PATH ?= $(THEOS)/makefiles
include $(THEOS_MAKE_PATH)/common.mk

TWEAK_NAME = ExampleTweak
ExampleTweak_FILES = Tweak.x
ExampleTweak_CFLAGS = -fobjc-arc
ExampleTweak_LIBRARIES = substrate

after-all::
	@echo "Build complete: ExampleTweak"

include $(THEOS_MAKE_PATH)/tweak.mk
