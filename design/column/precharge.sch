v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_lv_pmos.sym} -200 0 0 0 {name=MP0
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} -180 30 0 0 {name=l0 lab=BL}
C {devices/lab_pin.sym} -220 0 0 0 {name=l1 lab=PRE_B}
C {devices/lab_pin.sym} -180 -30 0 0 {name=l2 lab=VDD}
C {devices/lab_pin.sym} -180 0 0 0 {name=l3 lab=VDD}
C {sg13g2_pr/sg13_lv_pmos.sym} 0 0 0 0 {name=MP1
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 20 30 0 0 {name=l4 lab=BLB}
C {devices/lab_pin.sym} -20 0 0 0 {name=l5 lab=PRE_B}
C {devices/lab_pin.sym} 20 -30 0 0 {name=l6 lab=VDD}
C {devices/lab_pin.sym} 20 0 0 0 {name=l7 lab=VDD}
C {sg13g2_pr/sg13_lv_pmos.sym} 200 0 0 0 {name=MP2
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 220 30 0 0 {name=l8 lab=BL}
C {devices/lab_pin.sym} 180 0 0 0 {name=l9 lab=PRE_B}
C {devices/lab_pin.sym} 220 -30 0 0 {name=l10 lab=BLB}
C {devices/lab_pin.sym} 220 0 0 0 {name=l11 lab=VDD}
C {devices/ipin.sym} -900 -300 0 0 {name=p12 lab=PRE_B}
C {devices/iopin.sym} -900 -260 0 0 {name=p13 lab=BL}
C {devices/iopin.sym} -900 -220 0 0 {name=p14 lab=BLB}
C {devices/iopin.sym} -900 -180 0 0 {name=p15 lab=VDD}
C {devices/iopin.sym} -900 -140 0 0 {name=p16 lab=VSS}
C {devices/code_shown.sym} -900 0 0 0 {name=NOTE only_toplevel=false
place=header
value="* bit-line precharge to VDD and equalize, active-low PRE_B"}
