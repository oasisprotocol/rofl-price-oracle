# Root Makefile - thin delegator to oracle/Makefile
# The actual Python project lives in oracle/ (self-contained with pyproject.toml)

install:
	$(MAKE) -C oracle install

test:
	$(MAKE) -C oracle test

clean:
	$(MAKE) -C oracle clean
	rm -rf .venv  # Clean up legacy root venv if present

lint:
	$(MAKE) -C oracle lint

fmt:
	$(MAKE) -C oracle fmt

check:
	$(MAKE) -C oracle check

dist:
	$(MAKE) -C oracle dist

run:
	$(MAKE) -C oracle run

run-localnet:
	$(MAKE) -C oracle run-localnet

run-localnet-debug:
	$(MAKE) -C oracle run-localnet-debug

.PHONY: install test clean lint fmt check dist run run-localnet run-localnet-debug
