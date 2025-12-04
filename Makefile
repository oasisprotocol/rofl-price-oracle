# Install runtime + dev dependencies using uv
install:
	uv sync --all-extras

# Run tests (pytest)
test:
	uv run pytest oracle/tests

# Clean up build artifacts
clean:
	rm -rf __pycache__
	rm -rf oracle/__pycache__
	rm -rf oracle/src/__pycache__
	rm -rf oracle/tests/__pycache__
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache

# Lint code with Ruff
lint:
	uv run ruff check oracle/src oracle/tests

# Format code with Ruff
fmt:
	uv run ruff format oracle/src oracle/tests

# Run all checks (linting, testing)
check: lint test

# Create a distribution package
dist:
	uv build

# Run the application
run:
	uv run python -m oracle.main

