# steg-lab -- Kali Linux steganalysis knowledge base
PY := python3

.PHONY: help setup verify corpus test gates g0 g1 g2 g3 g4 g5 g6 g7 rust jpeg difftest bench docs clean dist

help:
	@echo "steg-lab targets:"
	@echo "  setup     install the Kali toolchain (scripts/setup-kali.sh)"
	@echo "  verify    check that the toolchain is actually usable"
	@echo "  corpus    regenerate the synthetic corpus from seeds"
	@echo "  test      run the pytest suite"
	@echo "  gates     run every gate runner"
	@echo "  g0 g1 g2 g3 g4 g5 g6 g7  run one gate"
	@echo "  rust      build and unit-test the stegscan crate"
	@echo "  jpeg      verify the JPEG entropy encoder"
	@echo "  difftest  Rust vs Python differential test"
	@echo "  bench     differential test with throughput comparison"
	@echo "  docs      run the six documentation checkers"
	@echo "  dist      build the release tarball"

setup:
	bash scripts/setup-kali.sh

verify:
	bash scripts/verify-toolchain.sh

corpus:
	$(PY) corpus/generate.py

test:
	$(PY) -m pytest tests -q

gates: g0 g1 g2 g3 g4 g5 g6 g7

g0:
	$(PY) gates/g0_wardens.py

g1:
	$(PY) gates/g1_parsers.py

g2:
	$(PY) gates/g2_classical.py

g3:
	$(PY) gates/g3_adaptive.py

g4:
	$(PY) gates/g4_statistical.py

g5:
	$(PY) gates/g5_feature_sets.py

g6:
	$(PY) gates/g6_deep_learning.py --n 160 --epochs 18

g7:
	$(PY) gates/g7_capstone.py

rust:
	cd rust/stegscan && cargo test --offline -q && cargo build --release --offline -q

jpeg:
	$(PY) scripts/verify-jpeg-encoder.py

difftest:
	$(PY) scripts/difftest.py --n 200

bench:
	$(PY) scripts/difftest.py --n 200 --bench

docs:
	$(PY) scripts/check-docs.py

clean:
	rm -rf corpus/generated gates/results rust/stegscan/target .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +

dist:
	bash scripts/make-dist.sh
