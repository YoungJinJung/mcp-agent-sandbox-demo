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
	python3 -m py_compile demo.py
