
# PIN installation
PIN_ROOT ?= $(HOME)/tools/pin-external-4.4-99977-g54fbb8814-gcc-linux
TRACER = Champsim/tracer/pin/obj-intel64/champsim_tracer.so
CHAMPSIM = ./Champsim/bin/champsim

# Experiment settings (override these when running make)
TRACE_INSTRUCTIONS ?= 25000000
WARMUP_INSTRUCTIONS ?= 5000000
SIMULATION_INSTRUCTIONS ?= 19999000
TRACE_SKIP_INSTRUCTIONS ?= 5000000
TRACE_MARGIN_INSTRUCTIONS ?= 1000
JAVA ?= java
JAVAC ?= javac
JAVA_OPTS ?= -Xshare:off -XX:+UseSerialGC -XX:-UseCompressedOops -XX:-UseCompressedClassPointers

CHECKPOINT_PROGRAMS ?= Sequential BranchPredictable BranchUnpredictable PointerChase DynamicDispatch
CHECKPOINT_LANGUAGES ?= python java

.PHONY: run-python run-java check checkpoint1

checkpoint1: check
	@mkdir -p traces results
	@set -e; \
	for language in $(CHECKPOINT_LANGUAGES); do \
		for program in $(CHECKPOINT_PROGRAMS); do \
			echo "Running checkpoint-1 $$language baseline: $$program"; \
			$(MAKE) PROGRAM=$$program run-$$language; \
		done; \
	done
	@echo "Checkpoint-1 baseline collection complete. Results are in ./results"

check:
	@test -x "$(PIN_ROOT)/pin" || (echo "PIN not found: check PIN_ROOT"; exit 1)
	@test -f "$(TRACER)" || (echo "PIN tracer not found"; exit 1)
	@test -x "$(CHAMPSIM)" || (echo "ChampSim executable not found"; exit 1)
	@mkdir -p traces results build/java

run-python: check
	@set -e; \
	if [ "$(TRACE_INSTRUCTIONS)" -lt "$$(( $(WARMUP_INSTRUCTIONS) + $(SIMULATION_INSTRUCTIONS) + $(TRACE_MARGIN_INSTRUCTIONS) ))" ]; then \
		echo "Trace limit must exceed warmup + simulation by at least $(TRACE_MARGIN_INSTRUCTIONS) instructions."; \
		exit 1; \
	fi; \
	TRACE="traces/python_$(PROGRAM)_skip$(TRACE_SKIP_INSTRUCTIONS)_$(TRACE_INSTRUCTIONS).champsim"; \
	RESULT="results/python_$(PROGRAM)_skip$(TRACE_SKIP_INSTRUCTIONS)_$(TRACE_INSTRUCTIONS).txt"; \
	echo "Generating Python trace: $(PROGRAM).py"; \
	"$(PIN_ROOT)/pin" -t "$(TRACER)" \
		-o "$$TRACE" -s "$(TRACE_SKIP_INSTRUCTIONS)" -t "$(TRACE_INSTRUCTIONS)" \
		-- python3 "programs/python/$(PROGRAM).py"; \
	ACTUAL_BYTES=$$(wc -c < "$$TRACE"); \
	EXPECTED_BYTES=$$(( $(TRACE_INSTRUCTIONS) * 64 )); \
	if [ "$$ACTUAL_BYTES" -ne "$$EXPECTED_BYTES" ]; then \
		echo "Incomplete trace for $(PROGRAM): expected $(TRACE_INSTRUCTIONS) records, got $$(( ACTUAL_BYTES / 64 ))."; \
		exit 1; \
	fi; \
	echo "Running ChampSim"; \
	"$(CHAMPSIM)" \
		--warmup-instructions "$(WARMUP_INSTRUCTIONS)" \
		--simulation-instructions "$(SIMULATION_INSTRUCTIONS)" \
		"$$TRACE" > "$$RESULT" 2>&1; \
	echo "Finished. Results: $$RESULT"

run-java: check
	@set -e; \
	if [ "$(TRACE_INSTRUCTIONS)" -lt "$$(( $(WARMUP_INSTRUCTIONS) + $(SIMULATION_INSTRUCTIONS) + $(TRACE_MARGIN_INSTRUCTIONS) ))" ]; then \
		echo "Trace limit must exceed warmup + simulation by at least $(TRACE_MARGIN_INSTRUCTIONS) instructions."; \
		exit 1; \
	fi; \
	echo "Compiling Java program: $(PROGRAM).java"; \
	$(JAVAC) -d build/java "programs/Java/$(PROGRAM).java"; \
	TRACE="traces/java_$(PROGRAM)_skip$(TRACE_SKIP_INSTRUCTIONS)_$(TRACE_INSTRUCTIONS).champsim"; \
	RESULT="results/java_$(PROGRAM)_skip$(TRACE_SKIP_INSTRUCTIONS)_$(TRACE_INSTRUCTIONS).txt"; \
	echo "Generating Java trace"; \
	"$(PIN_ROOT)/pin" -t "$(TRACER)" -thread_name checkpoint-main \
		-o "$$TRACE" -s "$(TRACE_SKIP_INSTRUCTIONS)" -t "$(TRACE_INSTRUCTIONS)" \
		-- $(JAVA) $(JAVA_OPTS) -cp build/java "$(PROGRAM)"; \
	ACTUAL_BYTES=$$(wc -c < "$$TRACE"); \
	EXPECTED_BYTES=$$(( $(TRACE_INSTRUCTIONS) * 64 )); \
	if [ "$$ACTUAL_BYTES" -ne "$$EXPECTED_BYTES" ]; then \
		echo "Incomplete trace for $(PROGRAM): expected $(TRACE_INSTRUCTIONS) records, got $$(( ACTUAL_BYTES / 64 ))."; \
		exit 1; \
	fi; \
	echo "Running ChampSim"; \
	"$(CHAMPSIM)" \
		--warmup-instructions "$(WARMUP_INSTRUCTIONS)" \
		--simulation-instructions "$(SIMULATION_INSTRUCTIONS)" \
		"$$TRACE" > "$$RESULT" 2>&1; \
	echo "Finished. Results: $$RESULT"
