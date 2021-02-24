CONFIG_DIR?=$(shell echo "$${XDG_CONFIG_HOME-$$HOME}/.config/i3expo")
PYTHON_FILES=$(wildcard *.py)
FORCE?=0

prtscn.so: prtscn.c
	gcc -shared -O3 -Wall -fPIC -Wl,-soname,prtscn -o prtscn.so prtscn.c -lX11

clean:
	rm prtscn.so


install: $(CONFIG_DIR) copy_default_config
	@echo "i3expo-ng installed to $(CONFIG_DIR)"

$(CONFIG_DIR): prtscn.so $(PYTHON_FILES)
	@echo "Installing to $(CONFIG_DIR)"
	mkdir -p $(CONFIG_DIR)
	cp prtscn.so $(PYTHON_FILES) $(CONFIG_DIR)

copy_default_config: defaultconfig
	@# Copy the config file only if it doesn't exists of if FORCE is set
	@if [ ! -f $(CONFIG_DIR)/config ] || [ $(FORCE) = 1 ]; then \
		echo cp defaultconfig $(CONFIG_DIR)/config ; \
		cp defaultconfig $(CONFIG_DIR)/config ; \
	else \
		echo "config file already exists! Run with FORCE=1 to overwrite"; \
	fi

uninstall:
	@echo -n "Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]
	rm -r $(CONFIG_DIR)

PHONY: clean install copy_default_config uninstall
