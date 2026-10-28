v {xschem version=3.4.8RC file_version=1.3}
G {}
K {}
V {}
S {}
E {}
C {gates/inv.sym} 0 0 0 0 {name=XCB}
C {devices/lab_pin.sym} -40.0 -30.0 0 0 {name=l0 lab=CLK}
C {devices/lab_pin.sym} -40.0 -10.0 0 0 {name=l1 lab=CLKB}
C {devices/lab_pin.sym} -40.0 10.0 0 0 {name=l2 lab=VDD}
C {devices/lab_pin.sym} -40.0 30.0 0 0 {name=l3 lab=VSS}
C {latches/dlatch.sym} 400 0 0 0 {name=XLA[7:0]}
C {devices/lab_pin.sym} 360.0 -50.0 0 0 {name=l4 lab=A[7:0]}
C {devices/lab_pin.sym} 360.0 -30.0 0 0 {name=l5 lab=CLKB}
C {devices/lab_pin.sym} 360.0 -10.0 0 0 {name=l6 lab=CLK}
C {devices/lab_pin.sym} 360.0 10.0 0 0 {name=l7 lab=AL[7:0]}
C {devices/lab_pin.sym} 360.0 30.0 0 0 {name=l8 lab=VDD}
C {devices/lab_pin.sym} 360.0 50.0 0 0 {name=l9 lab=VSS}
C {latches/dlatch.sym} 800 0 0 0 {name=XLC}
C {devices/lab_pin.sym} 760.0 -50.0 0 0 {name=l10 lab=CEN}
C {devices/lab_pin.sym} 760.0 -30.0 0 0 {name=l11 lab=CLKB}
C {devices/lab_pin.sym} 760.0 -10.0 0 0 {name=l12 lab=CLK}
C {devices/lab_pin.sym} 760.0 10.0 0 0 {name=l13 lab=CENL}
C {devices/lab_pin.sym} 760.0 30.0 0 0 {name=l14 lab=VDD}
C {devices/lab_pin.sym} 760.0 50.0 0 0 {name=l15 lab=VSS}
C {latches/dlatch.sym} 1200 0 0 0 {name=XLG}
C {devices/lab_pin.sym} 1160.0 -50.0 0 0 {name=l16 lab=GWEN}
C {devices/lab_pin.sym} 1160.0 -30.0 0 0 {name=l17 lab=CLKB}
C {devices/lab_pin.sym} 1160.0 -10.0 0 0 {name=l18 lab=CLK}
C {devices/lab_pin.sym} 1160.0 10.0 0 0 {name=l19 lab=GWENL}
C {devices/lab_pin.sym} 1160.0 30.0 0 0 {name=l20 lab=VDD}
C {devices/lab_pin.sym} 1160.0 50.0 0 0 {name=l21 lab=VSS}
C {latches/dlatch.sym} 0 240 0 0 {name=XLW}
C {devices/lab_pin.sym} -40.0 190.0 0 0 {name=l22 lab=WEN}
C {devices/lab_pin.sym} -40.0 210.0 0 0 {name=l23 lab=CLKB}
C {devices/lab_pin.sym} -40.0 230.0 0 0 {name=l24 lab=CLK}
C {devices/lab_pin.sym} -40.0 250.0 0 0 {name=l25 lab=WENL}
C {devices/lab_pin.sym} -40.0 270.0 0 0 {name=l26 lab=VDD}
C {devices/lab_pin.sym} -40.0 290.0 0 0 {name=l27 lab=VSS}
C {devices/ipin.sym} -900 -300 0 0 {name=p28 lab=CLK}
C {devices/ipin.sym} -900 -260 0 0 {name=p29 lab=A[7]}
C {devices/ipin.sym} -900 -220 0 0 {name=p30 lab=A[6]}
C {devices/ipin.sym} -900 -180 0 0 {name=p31 lab=A[5]}
C {devices/ipin.sym} -900 -140 0 0 {name=p32 lab=A[4]}
C {devices/ipin.sym} -900 -100 0 0 {name=p33 lab=A[3]}
C {devices/ipin.sym} -900 -60 0 0 {name=p34 lab=A[2]}
C {devices/ipin.sym} -900 -20 0 0 {name=p35 lab=A[1]}
C {devices/ipin.sym} -900 20 0 0 {name=p36 lab=A[0]}
C {devices/ipin.sym} -900 60 0 0 {name=p37 lab=CEN}
C {devices/ipin.sym} -900 100 0 0 {name=p38 lab=GWEN}
C {devices/ipin.sym} -900 140 0 0 {name=p39 lab=WEN}
C {devices/opin.sym} -900 180 0 0 {name=p40 lab=AL[7]}
C {devices/opin.sym} -900 220 0 0 {name=p41 lab=AL[6]}
C {devices/opin.sym} -900 260 0 0 {name=p42 lab=AL[5]}
C {devices/opin.sym} -900 300 0 0 {name=p43 lab=AL[4]}
C {devices/opin.sym} -900 340 0 0 {name=p44 lab=AL[3]}
C {devices/opin.sym} -900 380 0 0 {name=p45 lab=AL[2]}
C {devices/opin.sym} -900 420 0 0 {name=p46 lab=AL[1]}
C {devices/opin.sym} -900 460 0 0 {name=p47 lab=AL[0]}
C {devices/opin.sym} -900 500 0 0 {name=p48 lab=CENL}
C {devices/opin.sym} -900 540 0 0 {name=p49 lab=GWENL}
C {devices/opin.sym} -900 580 0 0 {name=p50 lab=WENL}
C {devices/iopin.sym} -900 620 0 0 {name=p51 lab=VDD}
C {devices/iopin.sym} -900 660 0 0 {name=p52 lab=VSS}
C {devices/code_shown.sym} -900 0 0 0 {name=NOTE only_toplevel=false
place=header
value="* address and control input latches, transparent while CLK is low, hold while CLK is high"}
