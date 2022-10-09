CONFIG_DIR?=$(shell echo "$${XDG_CONFIG_HOME-$$HOME}/i3expo")
CONFIG_FILE=$(CONFIG_DIR)/config
# The local files we need to install
TARGETS=prtscn.so i3expod.py
# Where to install
TARGET_DIR?=$(HOME)/.local/bin
# The final file paths
TARGET_PATHS?=$(TARGET_DIR)/prtscn.so $(TARGET_DIR)/i3expod.py
# Force the installation of config file?
FORCE?=0

prtscn.so: prtscn.c
	gcc -shared -O3 -Wall -fPIC -Wl,-soname,prtscn `pkg-config --cflags --libs python3` -o prtscn.so prtscn.c -lX11

clean:
	rm prtscn.so

install: pip3dependencies $(CONFIG_FILE) $(TARGET_PATHS) check_path

pip3dependencies:
	pip3 install -r requirements.txt

$(TARGET_PATHS): $(TARGETS)
	@echo "Installing to $(TARGET_DIR)"
	@mkdir -p $(TARGET_DIR)
	cp $(TARGETS) $(TARGET_DIR)
	@echo "i3expo-ng installed to $(TARGET_DIR)"

$(CONFIG_FILE): defaultconfig
	@# Copy the config file only if it doesn't exists of if FORCE is set
	@if [ ! -f $(CONFIG_FILE) ] || [ $(FORCE) = 1 ]; then \
		if [ -f $(CONFIG_FILE) ]; then \
			cp $(CONFIG_FILE) $(CONFIG_FILE).old; \
			echo "Old config maintained at $(CONFIG_FILE).old"; \
		fi; \
		mkdir -p $(CONFIG_DIR); \
		echo cp defaultconfig $(CONFIG_FILE) ; \
		cp defaultconfig $(CONFIG_FILE) ; \
	else \
		echo "config file already exists! Run with FORCE=1 to overwrite"; \
	fi

uninstall:
	@echo -n "Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]
	rm -r $(CONFIG_DIR) $(TARGET_PATHS)


check_path:
	@if [[ ! "${PATH}" == *"$(TARGET_DIR)"* ]]; then\
		echo "Looks like that $(TARGET_DIR) is not in your \$$PATH variable!";\
		echo "Run i3expo-ng daemon as $(TARGET_DIR)/i3expod.py";\
		fi

PHONY: clean install uninstall pip3dependencies check_path
