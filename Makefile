PYTHON ?= python
.PHONY: setup up status demo mutation test down ports
setup up status demo test down ports:
	$(PYTHON) scripts/manage.py $@
mutation:
	$(PYTHON) scripts/manage.py mutation --case $(CASE)
