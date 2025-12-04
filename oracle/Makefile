# Thin wrapper Makefile to keep legacy commands working when run from
# the oracle/ directory. All targets delegate to the root Makefile.

install:
	$(MAKE) -C .. install

test:
	$(MAKE) -C .. test

clean:
	$(MAKE) -C .. clean

lint:
	$(MAKE) -C .. lint

check:
	$(MAKE) -C .. check

dist:
	$(MAKE) -C .. dist

run:
	$(MAKE) -C .. run

run-localnet:
	@printf "$(CYAN)*** Starting $(BLUE)sapphire-localnet$(CYAN)...$(OFF)\n"
	@-docker run -it -p8545:8545 -p8546:8546 $(DOCKER_PLATFORM) ghcr.io/oasisprotocol/sapphire-localnet -test-mnemonic

run-localnet-debug:
	@printf "$(CYAN)*** Starting $(BLUE)sapphire-localnet$(CYAN) in $(MAGENTA)DEBUG$(CYAN) mode...$(OFF)\n"
	@-docker run -it -p8545:8545 -p8546:8546 $(DOCKER_PLATFORM) -e OASIS_NODE_LOG_LEVEL=debug -e LOG__LEVEL=debug ghcr.io/oasisprotocol/sapphire-localnet -test-mnemonic
