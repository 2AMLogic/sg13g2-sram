v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_lv_pmos.sym} -500 0 0 0 {name=MPI0
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} -480 30 0 0 {name=l0 lab=OUT}
C {devices/lab_pin.sym} -520 0 0 0 {name=l1 lab=SAE}
C {devices/lab_pin.sym} -480 -30 0 0 {name=l2 lab=BLM}
C {devices/lab_pin.sym} -480 0 0 0 {name=l3 lab=VDD}
C {sg13g2_pr/sg13_lv_pmos.sym} -300 0 0 0 {name=MPI1
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} -280 30 0 0 {name=l4 lab=OUTB}
C {devices/lab_pin.sym} -320 0 0 0 {name=l5 lab=SAE}
C {devices/lab_pin.sym} -280 -30 0 0 {name=l6 lab=BLBM}
C {devices/lab_pin.sym} -280 0 0 0 {name=l7 lab=VDD}
C {sg13g2_pr/sg13_lv_pmos.sym} -100 0 0 0 {name=MPL0
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} -80 30 0 0 {name=l8 lab=OUT}
C {devices/lab_pin.sym} -120 0 0 0 {name=l9 lab=OUTB}
C {devices/lab_pin.sym} -80 -30 0 0 {name=l10 lab=VDD}
C {devices/lab_pin.sym} -80 0 0 0 {name=l11 lab=VDD}
C {sg13g2_pr/sg13_lv_pmos.sym} 100 0 0 0 {name=MPL1
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 120 30 0 0 {name=l12 lab=OUTB}
C {devices/lab_pin.sym} 80 0 0 0 {name=l13 lab=OUT}
C {devices/lab_pin.sym} 120 -30 0 0 {name=l14 lab=VDD}
C {devices/lab_pin.sym} 120 0 0 0 {name=l15 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} 300 0 0 0 {name=MNL0
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 320 -30 0 0 {name=l16 lab=OUT}
C {devices/lab_pin.sym} 280 0 0 0 {name=l17 lab=OUTB}
C {devices/lab_pin.sym} 320 30 0 0 {name=l18 lab=TAIL}
C {devices/lab_pin.sym} 320 0 0 0 {name=l19 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} 500 0 0 0 {name=MNL1
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 520 -30 0 0 {name=l20 lab=OUTB}
C {devices/lab_pin.sym} 480 0 0 0 {name=l21 lab=OUT}
C {devices/lab_pin.sym} 520 30 0 0 {name=l22 lab=TAIL}
C {devices/lab_pin.sym} 520 0 0 0 {name=l23 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} 700 0 0 0 {name=MNT
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 720 -30 0 0 {name=l24 lab=TAIL}
C {devices/lab_pin.sym} 680 0 0 0 {name=l25 lab=SAE}
C {devices/lab_pin.sym} 720 30 0 0 {name=l26 lab=VSS}
C {devices/lab_pin.sym} 720 0 0 0 {name=l27 lab=VSS}
C {devices/ipin.sym} -900 -300 0 0 {name=p28 lab=SAE}
C {devices/iopin.sym} -900 -260 0 0 {name=p29 lab=BLM}
C {devices/iopin.sym} -900 -220 0 0 {name=p30 lab=BLBM}
C {devices/iopin.sym} -900 -180 0 0 {name=p31 lab=OUT}
C {devices/iopin.sym} -900 -140 0 0 {name=p32 lab=OUTB}
C {devices/iopin.sym} -900 -100 0 0 {name=p33 lab=VDD}
C {devices/iopin.sym} -900 -60 0 0 {name=p34 lab=VSS}
C {devices/code_shown.sym} -900 80 0 0 {name=NOTE only_toplevel=false
place=header
value="* latch sense amp: SAE low = isolation PMOS pass the bit-line pair to OUT/OUTB, SAE high = isolate and latch"}
