# Copyright 2015,2016 Gigaspaces
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Name of this package

PACKAGENAME = wagon

.PHONY: help
help:
	@echo 'Please use "make <target>" where <target> is one of'
	@echo "  release   - build a release and publish it"
	@echo "  dev       - prepare a development environment (includes tests)"
	@echo "  instdev   - prepare a development environment (no tests)"
	@echo "  install   - install into current Python environment"
	@echo "  test      - test from this directory using tox, including test coverage"
	@echo "  publish   - upload to PyPI"

.PHONY: release
release: publish
	@echo "$@ done."

.PHONY: dev
dev: instdev test
	@echo "$@ done."

.PHONY: instdev
instdev:
	pip install -r dev-requirements.txt
	python setup.py develop
	@echo "$@ done."

.PHONY: install
install:
	python setup.py install
	@echo "$@ done."

.PHONY: test
test:
	sudo pip install 'tox>=1.7.2'
	tox
	@echo "$@ done."

.PHONY: publish
publish:
	python setup.py sdist bdist_wheel
	twine upload -s dist/$(PACKAGENAME)-*
	@echo "$@ done."

.PHONY: clean
clean:
	rm -rf build $(PACKAGENAME).egg-info
	@echo "$@ done."
