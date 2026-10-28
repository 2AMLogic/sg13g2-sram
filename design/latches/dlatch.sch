v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
C {sg13g2_pr/sg13_lv_nmos.sym} 0 0 0 0 {name=MNI
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 20 -30 0 0 {name=l0 lab=N1}
C {devices/lab_pin.sym} -20 0 0 0 {name=l1 lab=EN}
C {devices/lab_pin.sym} 20 30 0 0 {name=l2 lab=D}
C {devices/lab_pin.sym} 20 0 0 0 {name=l3 lab=VSS}
C {sg13g2_pr/sg13_lv_pmos.sym} 200 0 0 0 {name=MPI
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 220 30 0 0 {name=l4 lab=N1}
C {devices/lab_pin.sym} 180 0 0 0 {name=l5 lab=ENB}
C {devices/lab_pin.sym} 220 -30 0 0 {name=l6 lab=D}
C {devices/lab_pin.sym} 220 0 0 0 {name=l7 lab=VDD}
C {sg13g2_pr/sg13_lv_pmos.sym} 400 0 0 0 {name=MP1
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 420 30 0 0 {name=l8 lab=QB}
C {devices/lab_pin.sym} 380 0 0 0 {name=l9 lab=N1}
C {devices/lab_pin.sym} 420 -30 0 0 {name=l10 lab=VDD}
C {devices/lab_pin.sym} 420 0 0 0 {name=l11 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} 600 0 0 0 {name=MN1
l=0.13u
w=0.5u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 620 -30 0 0 {name=l12 lab=QB}
C {devices/lab_pin.sym} 580 0 0 0 {name=l13 lab=N1}
C {devices/lab_pin.sym} 620 30 0 0 {name=l14 lab=VSS}
C {devices/lab_pin.sym} 620 0 0 0 {name=l15 lab=VSS}
C {sg13g2_pr/sg13_lv_pmos.sym} 800 0 0 0 {name=MP2
l=0.13u
w=1.0u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 820 30 0 0 {name=l16 lab=Q}
C {devices/lab_pin.sym} 780 0 0 0 {name=l17 lab=QB}
C {devices/lab_pin.sym} 820 -30 0 0 {name=l18 lab=VDD}
C {devices/lab_pin.sym} 820 0 0 0 {name=l19 lab=VDD}
C {sg13g2_pr/sg13_lv_nmos.sym} 1000 0 0 0 {name=MN2
l=0.13u
w=0.5u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 1020 -30 0 0 {name=l20 lab=Q}
C {devices/lab_pin.sym} 980 0 0 0 {name=l21 lab=QB}
C {devices/lab_pin.sym} 1020 30 0 0 {name=l22 lab=VSS}
C {devices/lab_pin.sym} 1020 0 0 0 {name=l23 lab=VSS}
C {sg13g2_pr/sg13_lv_nmos.sym} 1200 0 0 0 {name=MNF
l=0.13u
w=0.3u
ng=1
m=1
model=sg13_lv_nmos
spiceprefix=X}
C {devices/lab_pin.sym} 1220 -30 0 0 {name=l24 lab=N1}
C {devices/lab_pin.sym} 1180 0 0 0 {name=l25 lab=ENB}
C {devices/lab_pin.sym} 1220 30 0 0 {name=l26 lab=Q}
C {devices/lab_pin.sym} 1220 0 0 0 {name=l27 lab=VSS}
C {sg13g2_pr/sg13_lv_pmos.sym} 1400 0 0 0 {name=MPF
l=0.13u
w=0.3u
ng=1
m=1
model=sg13_lv_pmos
spiceprefix=X}
C {devices/lab_pin.sym} 1420 30 0 0 {name=l28 lab=N1}
C {devices/lab_pin.sym} 1380 0 0 0 {name=l29 lab=EN}
C {devices/lab_pin.sym} 1420 -30 0 0 {name=l30 lab=Q}
C {devices/lab_pin.sym} 1420 0 0 0 {name=l31 lab=VDD}
C {devices/ipin.sym} -900 -300 0 0 {name=p32 lab=D}
C {devices/ipin.sym} -900 -260 0 0 {name=p33 lab=EN}
C {devices/ipin.sym} -900 -220 0 0 {name=p34 lab=ENB}
C {devices/opin.sym} -900 -180 0 0 {name=p35 lab=Q}
C {devices/iopin.sym} -900 -140 0 0 {name=p36 lab=VDD}
C {devices/iopin.sym} -900 -100 0 0 {name=p37 lab=VSS}
C {devices/code_shown.sym} -900 0 0 0 {name=NOTE only_toplevel=false
place=header
value="* D latch: transparent while EN=1 (ENB=0); a weak feedback gate holds N1 when closed"}
