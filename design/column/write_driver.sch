v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_lv_pmos.sym} -600 -100 0 0 {name=MPD
l=0.13u
w=0.5u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} -580 -70 0 0 {name=l0 lab=DINB}
C {devices/lab_pin.sym} -620 -100 0 0 {name=l1 lab=DIN}
C {devices/lab_pin.sym} -580 -130 0 0 {name=l2 lab=VDD}
C {devices/lab_pin.sym} -580 -100 0 0 {name=l3 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} -600 100 0 0 {name=MND
l=0.13u
w=0.5u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} -580 70 0 0 {name=l4 lab=DINB}
C {devices/lab_pin.sym} -620 100 0 0 {name=l5 lab=DIN}
C {devices/lab_pin.sym} -580 130 0 0 {name=l6 lab=VSS}
C {devices/lab_pin.sym} -580 100 0 0 {name=l7 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} -200 -100 0 0 {name=MNA0
l=0.13u
w=3.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} -180 -130 0 0 {name=l8 lab=BLM}
C {devices/lab_pin.sym} -220 -100 0 0 {name=l9 lab=DINB}
C {devices/lab_pin.sym} -180 -70 0 0 {name=l10 lab=WA}
C {devices/lab_pin.sym} -180 -100 0 0 {name=l11 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} -200 100 0 0 {name=MNA1
l=0.13u
w=3.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} -180 70 0 0 {name=l12 lab=WA}
C {devices/lab_pin.sym} -220 100 0 0 {name=l13 lab=WE}
C {devices/lab_pin.sym} -180 130 0 0 {name=l14 lab=VSS}
C {devices/lab_pin.sym} -180 100 0 0 {name=l15 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} 200 -100 0 0 {name=MNB0
l=0.13u
w=3.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 220 -130 0 0 {name=l16 lab=BLBM}
C {devices/lab_pin.sym} 180 -100 0 0 {name=l17 lab=DIN}
C {devices/lab_pin.sym} 220 -70 0 0 {name=l18 lab=WB}
C {devices/lab_pin.sym} 220 -100 0 0 {name=l19 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} 200 100 0 0 {name=MNB1
l=0.13u
w=3.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 220 70 0 0 {name=l20 lab=WB}
C {devices/lab_pin.sym} 180 100 0 0 {name=l21 lab=WE}
C {devices/lab_pin.sym} 220 130 0 0 {name=l22 lab=VSS}
C {devices/lab_pin.sym} 220 100 0 0 {name=l23 lab=VSS}
C {devices/ipin.sym} -900 -300 0 0 {name=p24 lab=WE}
C {devices/ipin.sym} -900 -260 0 0 {name=p25 lab=DIN}
C {devices/iopin.sym} -900 -220 0 0 {name=p26 lab=BLM}
C {devices/iopin.sym} -900 -180 0 0 {name=p27 lab=BLBM}
C {devices/iopin.sym} -900 -140 0 0 {name=p28 lab=VDD}
C {devices/iopin.sym} -900 -100 0 0 {name=p29 lab=VSS}
C {devices/code_shown.sym} -900 40 0 0 {name=NOTE only_toplevel=false
place=header
value="* write driver: WE and DIN pull BLBM low, WE and DINB pull BLM low (cell Q takes DIN)"}
