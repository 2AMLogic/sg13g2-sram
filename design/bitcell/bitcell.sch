v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_lv_pmos.sym} -200 -150 0 0 {name=MP0
l=0.13u
w=0.15u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} -180 -120 0 0 {name=l_-180_-120 lab=Q}
C {devices/lab_pin.sym} -220 -150 0 0 {name=l_-220_-150 lab=QB}
C {devices/lab_pin.sym} -180 -180 0 0 {name=l_-180_-180 lab=VDD}
C {devices/lab_pin.sym} -180 -150 0 0 {name=l_-180_-150 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} -200 50 0 0 {name=MN0
l=0.13u
w=0.30u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} -180 20 0 0 {name=l_-180_20 lab=Q}
C {devices/lab_pin.sym} -220 50 0 0 {name=l_-220_50 lab=QB}
C {devices/lab_pin.sym} -180 80 0 0 {name=l_-180_80 lab=VSS}
C {devices/lab_pin.sym} -180 50 0 0 {name=l_-180_50 lab=VSS}
C {sg13g2_pr/sg13_lv_pmos.sym} 200 -150 0 0 {name=MP1
l=0.13u
w=0.15u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 220 -120 0 0 {name=l_220_-120 lab=QB}
C {devices/lab_pin.sym} 180 -150 0 0 {name=l_180_-150 lab=Q}
C {devices/lab_pin.sym} 220 -180 0 0 {name=l_220_-180 lab=VDD}
C {devices/lab_pin.sym} 220 -150 0 0 {name=l_220_-150 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} 200 50 0 0 {name=MN1
l=0.13u
w=0.30u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 220 20 0 0 {name=l_220_20 lab=QB}
C {devices/lab_pin.sym} 180 50 0 0 {name=l_180_50 lab=Q}
C {devices/lab_pin.sym} 220 80 0 0 {name=l_220_80 lab=VSS}
C {devices/lab_pin.sym} 220 50 0 0 {name=l_220_50 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} -400 -50 0 0 {name=MN2
l=0.13u
w=0.30u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} -380 -80 0 0 {name=l_-380_-80 lab=BL}
C {devices/lab_pin.sym} -420 -50 0 0 {name=l_-420_-50 lab=WL}
C {devices/lab_pin.sym} -380 -20 0 0 {name=l_-380_-20 lab=Q}
C {devices/lab_pin.sym} -380 -50 0 0 {name=l_-380_-50 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} 400 -50 0 0 {name=MN3
l=0.13u
w=0.30u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 420 -80 0 0 {name=l_420_-80 lab=BLB}
C {devices/lab_pin.sym} 380 -50 0 0 {name=l_380_-50 lab=WL}
C {devices/lab_pin.sym} 420 -20 0 0 {name=l_420_-20 lab=QB}
C {devices/lab_pin.sym} 420 -50 0 0 {name=l_420_-50 lab=VSS}
C {devices/iopin.sym} -600 -200 0 0 {name=p0 lab=BL}
C {devices/iopin.sym} -600 -160 0 0 {name=p1 lab=BLB}
C {devices/ipin.sym} -600 -120 0 0 {name=p2 lab=WL}
C {devices/iopin.sym} -600 -80 0 0 {name=p3 lab=VDD}
C {devices/iopin.sym} -600 -40 0 0 {name=p4 lab=VSS}
C {devices/iopin.sym} -600 0 0 0 {name=p5 lab=Q}
C {devices/iopin.sym} -600 40 0 0 {name=p6 lab=QB}
C {devices/code_shown.sym} -600 150 0 0 {name=NOTE only_toplevel=false
place=header
value="* 6T SRAM bitcell, reference sizing from spec/bitcell-decision.md evidence 1"}
