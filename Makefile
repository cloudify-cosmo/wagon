.PHONY: release install files test docs prepare publish

all:
	@echo "make release - prepares a release and publishes it"
	@echo "make dev - prepares a development environment (includes tests)"
	@echo "make instdev - prepares a development environment (no tests)"
	@echo "make install - install on local system"
	@echo "make test - run tox"
	@echo "make docs - build docs"
	@echo "prepare - prepare module for release (CURRENTLY IRRELEVANT)"
	@echo "make publish - upload to pypi"

release: docs publish

dev: instdev test

instdev:
	pip install -rdev-requirements.txt
	python setup.py develop

install:
	python setup.py install

test:
	pip install tox
	tox

docs:
	pandoc README.md -f markdown -t rst -s -o README.rst

prepare:
	python scripts/make-release.py

publish:
	python setup.py sdist upload