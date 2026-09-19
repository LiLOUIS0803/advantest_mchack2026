import common.GroupAndVar;

spec levels {

  set levelSet1;
  setup digInOut AllPins{
     connect = true;
     set level levelSet1 {
       vih = _DpsVout;
       vil= 0.0 V;
       voh= _DpsVout*0.8;
       vol= _DpsVout*0.2;
     }
  }
  setup digInOut CP{
     connect = true;
     set level levelSet1 {
       vih = _DpsVout;
       vil= 0.1 V;
       voh= _DpsVout*0.8;
       vol= _DpsVout*0.2;

     }
  }
  setup dcVI VCC
  {

     level.vrange = 5 V;
     level.irange = 25 mA;
     connect = true;

  }





}
