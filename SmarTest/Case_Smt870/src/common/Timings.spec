import common.GroupAndVar;
spec Timings {
   set timingSet_1;
   setup digInOut AllPins{
       wavetable wvt1{
           xModes = 1 {
               0: d1:0;
               1: d1:1;
               L: d1:Z r1:L;
               H: d1:Z r1:H;
               X: d1:Z r1:X;
           }

       }
       set timing timingSet_1{
           period = _per;
           d1= 0.0 ns;
           r1=  _per / 2;
       }

   }
}
