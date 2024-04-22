# Copyleft
# Solderpad Hardware License, Version 0.51, see LICENSE for details.
# SPDX-License-Identifier: SHL-0.51
#


MKFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
MKFILE_DIR  := $(dir $(MKFILE_PATH))
ROOT        := ${MKFILE_DIR}../../../..
CVA6_SDK    ?= ${ROOT}/../cva6-sdk
DEBUG       ?= 0
EXT_JTAG    ?= 0
VCU         ?= 01
FPGA_ID     := 091847100576A
HW_SERVER   := bordcomputer:3231


BENDER_TARGETS += -t cv64a6_imafdc_sv39 -t occamy

sources.tcl: Makefile
	${MAKE} -C ../sim rtl
	bender script vivado $(BENDER_TARGETS) > $@

.PHONY: vivado_lint

vivado_lint: sources.tcl
	rm -rf vivado && mkdir -p vivado
	@echo "synth_design -rtl -rtl_skip_mlo -name rtl_1" >launch_runs.tcl
	vivado -mode batch -source ./create_project.tcl ./launch_runs.tcl | tee vivado.log

vivado_prj: sources.tcl
	rm -rf vivado && mkdir -p vivado
	@echo "synth_design -rtl -rtl_skip_mlo -name rtl_1" >launch_runs.tcl
	vivado -mode batch -source ./create_project.tcl  | tee vivado.log

.PHONY: vivado_clean
vivado_clean:
	rm -f vivado.*
	rm -fr vivado/
	rm -f sources.tcl
	${MAKE} -C ../sim clean-rtl
	