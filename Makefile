HARNESS ?= ../harness
B := $(HARNESS)/plugins/fleet-control/skills
FLEET := lights-out

.PHONY: check audit room collect skeleton
check:  ## schema, contract and source coverage
	@python3 -c "import json,jsonschema,pathlib; 	  jsonschema.Draft202012Validator(json.loads(pathlib.Path('$(B)/fleet-intent/references/intent.schema.json').read_text()))	  .validate(json.loads(pathlib.Path('intent/$(FLEET).intent.json').read_text())); print('schema ok')"
	@python3 $(B)/fleet-scaffold/references/scaffold.py intent/$(FLEET).intent.json data data/$(FLEET).data.json check
	@HARNESS=$(HARNESS) python3 collector/collect.py --check

audit:  ## ranked gaps against the declared standard
	@python3 $(B)/fleet-audit/references/audit.py intent/$(FLEET).intent.json data/$(FLEET).data.json

room:   ## regenerate the control room
	@python3 $(B)/fleet-surface/references/build.py intent/$(FLEET).intent.json data/$(FLEET).data.json site/control-room.html

collect:  ## run the adapters and refresh the data file
	@HARNESS=$(HARNESS) python3 collector/collect.py

skeleton:  ## honest day-one record: make skeleton ID=my-thing CLASS=1
	@python3 $(B)/fleet-scaffold/references/scaffold.py intent/$(FLEET).intent.json instance $(ID) --class $(CLASS)
