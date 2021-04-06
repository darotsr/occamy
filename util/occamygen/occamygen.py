#!/usr/bin/env python3

# Copyright 2020 ETH Zurich and University of Bologna.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

import argparse
import hjson
import pathlib
import sys
import re

from jsonref import JsonRef
from clustergen.occamy import Occamy
from mako.lookup import TemplateLookup

from solder import solder

templates = TemplateLookup(
    directories=[pathlib.Path(__file__).parent / "../hw/system/occamy/src"],
    output_encoding="utf-8")


def main():
    """Generate the Occamy system and all corresponding configuration files."""
    parser = argparse.ArgumentParser(prog="clustergen")
    parser.add_argument("--clustercfg",
                        "-c",
                        metavar="file",
                        type=argparse.FileType('r'),
                        required=True,
                        help="A cluster configuration file")
    parser.add_argument("--outdir",
                        "-o",
                        type=pathlib.Path,
                        required=True,
                        help="Target directory.")

    # Parse arguments.
    parser.add_argument("TOP_SV", help="Name of top-level file (output).")
    parser.add_argument("PKG_SV",
                        help="Name of top-level package file (output)")
    parser.add_argument("QUADRANT_S1",
                        help="Name of S1 quadrant file (output)")
    parser.add_argument("XILINX_SV", help="Name of the Xilinx wrapper file (output).")
    parser.add_argument("--graph", "-g", metavar="DOT")
    parser.add_argument("--cheader", "-D", metavar="CHEADER")

    args = parser.parse_args()
    # Read HJSON description
    with args.clustercfg as file:
        try:
            srcfull = file.read()
            obj = hjson.loads(srcfull, use_decimal=True)
            obj = JsonRef.replace_refs(obj)
        except ValueError:
            raise SystemExit(sys.exc_info()[1])

    occamy = Occamy(obj)

    # Arguments.
    nr_s1_quadrants = occamy.cfg["nr_s1_quadrant"]
    nr_s1_clusters = occamy.cfg["s1_quadrant"]["nr_clusters"]

    if not args.outdir.is_dir():
        exit("Out directory is not a valid path.")

    outdir = args.outdir / "src"
    outdir.mkdir(parents=True, exist_ok=True)

    with open(outdir / "occamy_cluster_wrapper.sv", "w") as f:
        f.write(occamy.render_wrapper())

    with open(outdir / "memories.json", "w") as f:
        f.write(occamy.cluster.memory_cfg())

    # Compile a regex to trim trailing whitespaces on lines.
    re_trailws = re.compile(r'[ \t\r]+$', re.MULTILINE)

    # Setup the templating engine.
    tpl_top = templates.get_template("occamy_top.sv.tpl")
    tpl_quadrant_s1 = templates.get_template("occamy_quadrant_s1.sv.tpl")
    tpl_pkg = templates.get_template("occamy_pkg.sv.tpl")
    tpl_xilinx = templates.get_template("occamy_xilinx.sv.tpl")

    # Create the address map.
    am = solder.AddrMap()

    am_soc_periph_regbus_xbar = am.new_node("soc_periph_regbus_xbar")
    am_soc_narrow_xbar = am.new_node("soc_narrow_xbar")
    am_soc_wide_xbar = am.new_node("soc_wide_xbar")

    am_debug = am.new_leaf("debug", 0x1000,
                           0x00000000).attach_to(am_soc_periph_regbus_xbar)
    am_bootrom = am.new_leaf("bootrom", 0x10000,
                             0x00010000).attach_to(am_soc_periph_regbus_xbar)
    am_soc_ctrl = am.new_leaf("soc_ctrl", 0x1000,
                              0x00020000).attach_to(am_soc_periph_regbus_xbar)
    am_plic = am.new_leaf("plic", 0x1000,
                          0x00024000).attach_to(am_soc_periph_regbus_xbar)
    am_uart = am.new_leaf("uart", 0x1000,
                          0x00030000).attach_to(am_soc_periph_regbus_xbar)
    am_gpio = am.new_leaf("gpio", 0x1000,
                          0x00031000).attach_to(am_soc_periph_regbus_xbar)
    am_i2c = am.new_leaf("i2c", 0x1000,
                         0x00033000).attach_to(am_soc_periph_regbus_xbar)
    am_clint = am.new_leaf("clint", 0x10000,
                           0x00040000).attach_to(am_soc_periph_regbus_xbar)

    am_pcie = am.new_leaf("pcie", 0x80000000,
                          0x80000000).attach_to(am_soc_wide_xbar)

    am_soc_narrow_xbar.attach(am_soc_periph_regbus_xbar)
    am_soc_narrow_xbar.attach(am_soc_wide_xbar)

    # Generate crossbars.

    #######################
    # SoC Peripheral Xbar #
    #######################
    soc_periph_xbar = solder.AxiLiteXbar(48,
                                         64,
                                         name="soc_periph_xbar",
                                         clk="clk_i",
                                         rst="rst_ni",
                                         node=am_soc_periph_regbus_xbar)

    # Peripherals crossbar (peripheral clock domain).
    soc_periph_xbar.add_input("soc")
    soc_periph_xbar.add_output_entry("soc_ctrl", am_soc_ctrl)
    soc_periph_xbar.add_output_entry("debug", am_debug)
    soc_periph_xbar.add_output_entry("bootrom", am_bootrom)
    soc_periph_xbar.add_output_entry("clint", am_clint)
    soc_periph_xbar.add_output_entry("plic", am_plic)
    soc_periph_xbar.add_output_entry("uart", am_uart)
    soc_periph_xbar.add_output_entry("gpio", am_gpio)
    soc_periph_xbar.add_output_entry("i2c", am_i2c)

    #################
    # SoC Wide Xbar #
    #################
    soc_wide_xbar = solder.AxiXbar(48,
                                   512,
                                   3,
                                   name="soc_wide_xbar",
                                   clk="clk_i",
                                   rst="rst_ni",
                                   no_loopback=True,
                                   node=am_soc_wide_xbar)

    for i in range(nr_s1_quadrants):
        soc_wide_xbar.add_output_symbolic("s1_quadrant_{}".format(i),
                                          "s1_quadrant_base_addr",
                                          "S1QuadrantAddressSpace")
        soc_wide_xbar.add_input("s1_quadrant_{}".format(i))

    soc_wide_xbar.add_input("soc_narrow")
    # TODO(zarubaf): PCIe should probably go into the small crossbar.
    soc_wide_xbar.add_input("pcie")
    soc_wide_xbar.add_output_entry("pcie", am_pcie)
    ###################
    # SoC Narrow Xbar #
    ###################
    soc_narrow_xbar = solder.AxiXbar(48,
                                     64,
                                     4,
                                     name="soc_narrow_xbar",
                                     clk="clk_i",
                                     rst="rst_ni",
                                     no_loopback=True,
                                     node=am_soc_narrow_xbar)

    for i in range(nr_s1_quadrants):
        soc_narrow_xbar.add_output_symbolic("s1_quadrant_{}".format(i),
                                            "s1_quadrant_base_addr",
                                            "S1QuadrantAddressSpace")
        soc_narrow_xbar.add_input("s1_quadrant_{}".format(i))

    soc_narrow_xbar.add_output_entry("periph", am_soc_periph_regbus_xbar)
    soc_narrow_xbar.add_output_entry("soc_wide", am_soc_wide_xbar)

    soc_narrow_xbar.add_input("cva6")

    ################
    # S1 Quadrants #
    ################
    # Dummy entries to generate associated types.
    wide_xbar_quadrant_s1 = solder.AxiXbar(
        48,
        512,
        3,  # TODO: Source from JSON description
        name="wide_xbar_quadrant_s1",
        clk="clk_i",
        rst="rst_ni",
        no_loopback=True,
        context="quadrant_s1")

    narrow_xbar_quadrant_s1 = solder.AxiXbar(
        48,
        64,
        4,  # TODO: Source from JSON description
        name="narrow_xbar_quadrant_s1",
        clk="clk_i",
        rst="rst_ni",
        no_loopback=True,
        context="quadrant_s1")

    wide_xbar_quadrant_s1.add_output("top", [])
    wide_xbar_quadrant_s1.add_input("top")
    narrow_xbar_quadrant_s1.add_output("top", [])
    narrow_xbar_quadrant_s1.add_input("top")

    for i in range(nr_s1_clusters):
        wide_xbar_quadrant_s1.add_output_symbolic("cluster_{}".format(i),
                                                  "cluster_base_addr",
                                                  "ClusterAddressSpace")
        wide_xbar_quadrant_s1.add_input("cluster_{}".format(i))
        narrow_xbar_quadrant_s1.add_output_symbolic("cluster_{}".format(i),
                                                    "cluster_base_addr",
                                                    "ClusterAddressSpace")
        narrow_xbar_quadrant_s1.add_input("cluster_{}".format(i))

    # Generate the Verilog code.
    solder.render()

    # Emit the code.
    with open(args.TOP_SV, "w") as file:
        code = tpl_top.render_unicode(
            module=solder.code_module['default'].replace("\n", "\n  "),
            solder=solder,
            soc_periph_xbar=soc_periph_xbar,
            soc_wide_xbar=soc_wide_xbar,
            soc_narrow_xbar=soc_narrow_xbar,
            nr_s1_quadrants=nr_s1_quadrants)
        code = re_trailws.sub("", code)
        file.write(code)

    # print(solder.code_module)
    with open(args.QUADRANT_S1, "w") as file:
        code = tpl_quadrant_s1.render_unicode(
            module=solder.code_module['quadrant_s1'].replace("\n", "\n  "),
            solder=solder,
            soc_wide_xbar=soc_wide_xbar,
            soc_narrow_xbar=soc_narrow_xbar,
            wide_xbar_quadrant_s1=wide_xbar_quadrant_s1,
            narrow_xbar_quadrant_s1=narrow_xbar_quadrant_s1,
            nr_clusters=nr_s1_clusters,
            const_cache_cfg=occamy.cfg["s1_quadrant"].get("const_cache"))
        code = re_trailws.sub("", code)
        file.write(code)

    with open(args.PKG_SV, "w") as file:
        code = tpl_pkg.render_unicode(
            package=solder.code_package.replace("\n", "\n  "),
            solder=solder,
        )
        code = re_trailws.sub("", code)
        file.write(code)

    with open(args.XILINX_SV, "w") as file:
        code = tpl_xilinx.render_unicode(
            solder=solder,
            soc_wide_xbar=soc_wide_xbar,
        )
        code = re_trailws.sub("", code)
        file.write(code)

    if args.cheader:
        with open(args.cheader, "w") as file:
            file.write(am.print_cheader())

    # Emit the address map as a dot file if requested.
    if args.graph:
        with open(args.graph, "w") as file:
            file.write(am.render_graphviz())


if __name__ == "__main__":
    main()