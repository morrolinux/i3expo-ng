CONFIG_DIR?=$(shell echo "$${XDG_CONFIG_HOME-$$HOME/.config}/i3expo")
CONFIG_FILE=$(CONFIG_DIR)/config
# Force the installation of config file?
FORCE?=0

PYTHON=python3
PIP=$(PYTHON) -m pip

pip3dependencies:
	$(PIP) install -r requirements.txt

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

build:
	$(PYTHON) setup.py sdist

install: pip3dependencies $(CONFIG_FILE) build
	$(PIP) install .

uninstall:
	@echo -n "Are you sure? [y/N] " && read ans && [ $${ans:-N} = y ]
	$(PIP) uninstall i3expod

clean:
	$(PYTHON) setup.py clean
	rm -rf build
	rm -rf dist
	rm -rf i3expod.egg-info

PHONY: clean install uninstall pip3dependencies $(CONFIG_FILE)
