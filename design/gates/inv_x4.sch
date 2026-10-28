v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_lv_pmos.sym} 0 0 0 0 {name=MP
l=0.13u
w=4.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 20 30 0 0 {name=l0 lab=Y}
C {devices/lab_pin.sym} -20 0 0 0 {name=l1 lab=A}
C {devices/lab_pin.sym} 20 -30 0 0 {name=l2 lab=VDD}
C {devices/lab_pin.sym} 20 0 0 0 {name=l3 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} 200 0 0 0 {name=MN
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 220 -30 0 0 {name=l4 lab=Y}
C {devices/lab_pin.sym} 180 0 0 0 {name=l5 lab=A}
C {devices/lab_pin.sym} 220 30 0 0 {name=l6 lab=VSS}
C {devices/lab_pin.sym} 220 0 0 0 {name=l7 lab=VSS}
C {devices/ipin.sym} -900 -300 0 0 {name=p8 lab=A}
C {devices/opin.sym} -900 -260 0 0 {name=p9 lab=Y}
C {devices/iopin.sym} -900 -220 0 0 {name=p10 lab=VDD}
C {devices/iopin.sym} -900 -180 0 0 {name=p11 lab=VSS}
C {devices/code_shown.sym} -900 0 0 0 {name=NOTE only_toplevel=false
place=header
value="* inverter, 4x drive: N 2.0 um / P 4.0 um"}
