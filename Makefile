#!/usr/bin/make
# WARN: gmake syntax
########################################################
# Makefile for pyeapi
#
# useful targets:
#	make rpm -- build RPM for EOS switches
#	make swix -- package RPM as a swix
#	make sdist -- build python source distribution
#	make pep8 -- pep8 checks
#	make pyflakes -- pyflakes checks
#	make flake8 -- flake8 checks
#	make check -- manifest checks
#	make tests -- run all of the tests
#	make unittest -- runs the unit tests
#	make systest -- runs the system tests
#	make clean -- clean distutils
#
########################################################
# variable section

NAME = "intelligent-bypass-l3"

PYTHON=python
COVERAGE=coverage
SITELIB = $(shell $(PYTHON) -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")

VERSION := $(shell cat VERSION)
RPMRELEASE := 1

# RPM build defines
TOPDIR = $(shell pwd)
RPMSPECDIR := $(TOPDIR)
RPMSPEC := $(RPMSPECDIR)/intelligent-bypass-l3.spec
RPM_TARGET := noarch
BASENAME := $(NAME)-$(VERSION)-$(RPMRELEASE)
EOSRPM := $(BASENAME).$(RPM_TARGET).rpm
SWIX := $(BASENAME).swix

########################################################

all: clean check pep8 pyflakes tests

pep8:
	-pep8 -r --ignore=E501,E221,W291,W391,E302,E251,E203,W293,E231,E303,E201,E225,E261,E241 . test/

pyflakes:
	pyflakes . test/

flake8:
	flake8 --ignore=E302,E303,W391 --exit-zero .
	flake8 --ignore=E302,E303,W391,N802 --max-line-length=100 test/

check:
	check-manifest

clean:
	@echo "Cleaning up build/dist/rpmbuild..."
	rm -rf $(TMPDIR)/build/$(BASENAME)
	rm -rf build dist rpmbuild
	rm -f manifest.txt $(SWIX) $(EOSRPM) $(PAM_EOS_RPM) $(PAM_RPM_NAME).*.src.rpm
	rm -rf *.egg-info
	@echo "Cleaning up byte compiled python stuff"
	find . -type f -regex ".*\.py[co]$$" -delete

sdist: clean
	$(PYTHON) setup.py sdist

tests: unittest systest

unittest: clean
	$(COVERAGE) run -m unittest discover test/unit -v

systest: clean
	$(COVERAGE) run -m unittest discover test/system -v

coverage_report:
	$(COVERAGE) report -m

all: clean swix

rpm: $(EOSRPM)

swix: $(SWIX)

$(SWIX): $(EOSRPM) $(PAM_EOS_RPM) manifest.txt
	zip -9 $@ $^
	rm -f $(PAM_EOS_RPM)

manifest.txt:
	set -e; { \
          echo 'format: 1'; \
          echo 'primaryRpm: $(EOSRPM)'; \
          echo -n '$(EOSRPM)-sha1: '; \
          set `$(SHA1SUM) "$(EOSRPM)"`; \
          echo $$1; \
          echo -n '$(PAM_EOS_RPM)-sha1: '; \
          set `$(SHA1SUM) $(PAM_EOS_RPM)`; \
          echo $$1; \
        } >$@-t
	mv $@-t $@

rpmcommon: sdist
	mkdir -p rpmbuild
	sed -e 's#^Version:.*#Version: $(VERSION)#' \
	    -e 's#^Release:.*#Release: $(RPMRELEASE)#' $(RPMSPEC) > rpmbuild/$(NAME).spec
	mv dist/$(NAME)-$(VERSION).tar.gz dist/$(BASENAME).tar.gz

$(EOSRPM): rpmcommon
	@rpmbuild --define "_topdir %(pwd)/rpmbuild" \
	--define "_specdir $(RPMSPECDIR)" \
	--define "_sourcedir %(pwd)/dist/" \
	--define "_rpmdir %(pwd)" \
	--define "_srcrpmdir %{_topdir}" \
	--define "_rpmfilename %%{NAME}-%%{VERSION}-%%{RELEASE}.%%{ARCH}.rpm" \
	--define "__python /usr/bin/python" \
	-bb rpmbuild/$(NAME).spec
	@rm -f rpmbuild/$(NAME).spec

