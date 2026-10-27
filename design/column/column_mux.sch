v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_lv_nmos.sym} -400 -100 0 0 {name=MN0T
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} -380 -130 0 0 {name=l0 lab=BL0}
C {devices/lab_pin.sym} -420 -100 0 0 {name=l1 lab=SEL0}
C {devices/lab_pin.sym} -380 -70 0 0 {name=l2 lab=BLM}
C {devices/lab_pin.sym} -380 -100 0 0 {name=l3 lab=VSS}
C {sg13g2_pr/sg13_lv_pmos.sym} -400 100 0 0 {name=MP0T
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} -380 130 0 0 {name=l4 lab=BL0}
C {devices/lab_pin.sym} -420 100 0 0 {name=l5 lab=SEL0B}
C {devices/lab_pin.sym} -380 70 0 0 {name=l6 lab=BLM}
C {devices/lab_pin.sym} -380 100 0 0 {name=l7 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} -150 -100 0 0 {name=MN0B
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} -130 -130 0 0 {name=l8 lab=BLB0}
C {devices/lab_pin.sym} -170 -100 0 0 {name=l9 lab=SEL0}
C {devices/lab_pin.sym} -130 -70 0 0 {name=l10 lab=BLBM}
C {devices/lab_pin.sym} -130 -100 0 0 {name=l11 lab=VSS}
C {sg13g2_pr/sg13_lv_pmos.sym} -150 100 0 0 {name=MP0B
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} -130 130 0 0 {name=l12 lab=BLB0}
C {devices/lab_pin.sym} -170 100 0 0 {name=l13 lab=SEL0B}
C {devices/lab_pin.sym} -130 70 0 0 {name=l14 lab=BLBM}
C {devices/lab_pin.sym} -130 100 0 0 {name=l15 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} 100 -100 0 0 {name=MN1T
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 120 -130 0 0 {name=l16 lab=BL1}
C {devices/lab_pin.sym} 80 -100 0 0 {name=l17 lab=SEL1}
C {devices/lab_pin.sym} 120 -70 0 0 {name=l18 lab=BLM}
C {devices/lab_pin.sym} 120 -100 0 0 {name=l19 lab=VSS}
C {sg13g2_pr/sg13_lv_pmos.sym} 100 100 0 0 {name=MP1T
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 120 130 0 0 {name=l20 lab=BL1}
C {devices/lab_pin.sym} 80 100 0 0 {name=l21 lab=SEL1B}
C {devices/lab_pin.sym} 120 70 0 0 {name=l22 lab=BLM}
C {devices/lab_pin.sym} 120 100 0 0 {name=l23 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} 350 -100 0 0 {name=MN1B
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 370 -130 0 0 {name=l24 lab=BLB1}
C {devices/lab_pin.sym} 330 -100 0 0 {name=l25 lab=SEL1}
C {devices/lab_pin.sym} 370 -70 0 0 {name=l26 lab=BLBM}
C {devices/lab_pin.sym} 370 -100 0 0 {name=l27 lab=VSS}
C {sg13g2_pr/sg13_lv_pmos.sym} 350 100 0 0 {name=MP1B
l=0.13u
w=2.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 370 130 0 0 {name=l28 lab=BLB1}
C {devices/lab_pin.sym} 330 100 0 0 {name=l29 lab=SEL1B}
C {devices/lab_pin.sym} 370 70 0 0 {name=l30 lab=BLBM}
C {devices/lab_pin.sym} 370 100 0 0 {name=l31 lab=VDD}
C {devices/ipin.sym} -900 -300 0 0 {name=p32 lab=SEL0}
C {devices/ipin.sym} -900 -260 0 0 {name=p33 lab=SEL0B}
C {devices/ipin.sym} -900 -220 0 0 {name=p34 lab=SEL1}
C {devices/ipin.sym} -900 -180 0 0 {name=p35 lab=SEL1B}
C {devices/iopin.sym} -900 -140 0 0 {name=p36 lab=BL0}
C {devices/iopin.sym} -900 -100 0 0 {name=p37 lab=BLB0}
C {devices/iopin.sym} -900 -60 0 0 {name=p38 lab=BL1}
C {devices/iopin.sym} -900 -20 0 0 {name=p39 lab=BLB1}
C {devices/iopin.sym} -900 20 0 0 {name=p40 lab=BLM}
C {devices/iopin.sym} -900 60 0 0 {name=p41 lab=BLBM}
C {devices/iopin.sym} -900 100 0 0 {name=p42 lab=VDD}
C {devices/iopin.sym} -900 140 0 0 {name=p43 lab=VSS}
C {devices/code_shown.sym} -900 280 0 0 {name=NOTE only_toplevel=false
place=header
value="* 2:1 column mux: NMOS+PMOS transmission gates, SELn high / SELnB low selects column n"}
