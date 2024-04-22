create_project isolde-zcu102 ./vivado/isolde-zcu102 -part xczu9eg-ffvb1156-2-e -force
source sources.tcl
set_property top occamy_cluster_wrapper [current_fileset]
update_compile_order -fileset sources_1
if {[regexp -nocase {.*board_part.*} [list_property [current_project]]]} {
  set_property board_part xilinx.com:zcu102:part0:3.4 [current_project]
} else {
  set_property board xilinx.com:zcu102:part0:3.4 [current_project]
}