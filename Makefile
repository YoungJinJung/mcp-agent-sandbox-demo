.PHONY: up demo status down check
up:
	./scripts/demo.sh up
demo:
	./scripts/demo.sh run
status:
	./scripts/demo.sh status
down:
	./scripts/demo.sh down
check:
	bash -n scripts/demo.sh
	python3 -m py_compile demo.py scripts/floci.py devtools/ci_demo.py devtools/sample/*.py

.PHONY: floci-up floci-demo floci-ci floci-status floci-down
floci-up:
	DEMO_BACKEND=floci ./scripts/demo.sh up
floci-demo:
	DEMO_BACKEND=floci ./scripts/demo.sh run
floci-ci:
	DEMO_BACKEND=floci ./scripts/demo.sh ci
floci-status:
	DEMO_BACKEND=floci ./scripts/demo.sh status
floci-down:
	DEMO_BACKEND=floci ./scripts/demo.sh down
