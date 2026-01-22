# Oracle project Makefile - the real implementation
# pyproject.toml and uv.lock live here; this is the self-contained Python project

# Install runtime + dev dependencies using uv
install:
	uv sync --all-extras

# Run tests (pytest)
test:
	uv run pytest tests

# Clean up build artifacts
clean:
	rm -rf __pycache__
	rm -rf oracle/__pycache__
	rm -rf oracle/fetchers/__pycache__
	rm -rf tests/__pycache__
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache

# Lint code with Ruff
lint:
	uv run ruff check oracle tests

# Format code with Ruff
fmt:
	uv run ruff format oracle tests

# Run all checks (linting, testing)
check: lint test

# Create a distribution package
dist:
	uv build

# Run the application
run:
	uv run python -m oracle.main

# Run sapphire-localnet for local development
run-localnet:
	@printf "\033[36m*** Starting \033[34msapphire-localnet\033[36m...\033[0m\n"
	@-docker run -it -p8545:8545 -p8546:8546 $(DOCKER_PLATFORM) ghcr.io/oasisprotocol/sapphire-localnet -test-mnemonic

# Run sapphire-localnet in debug mode
run-localnet-debug:
	@printf "\033[36m*** Starting \033[34msapphire-localnet\033[36m in \033[35mDEBUG\033[36m mode...\033[0m\n"
	@-docker run -it -p8545:8545 -p8546:8546 $(DOCKER_PLATFORM) -e OASIS_NODE_LOG_LEVEL=debug -e LOG__LEVEL=debug ghcr.io/oasisprotocol/sapphire-localnet -test-mnemonic

.PHONY: install test clean lint fmt check dist run run-localnet run-localnet-debug
