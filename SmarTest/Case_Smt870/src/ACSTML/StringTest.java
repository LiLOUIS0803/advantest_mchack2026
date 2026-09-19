package ACSTML;

import java.nio.charset.StandardCharsets;

import xoc.dta.TestMethod;
import xoc.dta.datatypes.MultiSiteLong;
import xoc.dta.datatypes.MultiSiteString;
import xoc.dta.testdescriptor.IParametricTestDescriptor;

public class StringTest extends TestMethod {

    public String tpVar="lotid";

    public IParametricTestDescriptor LowerTestDescriptor;
    public IParametricTestDescriptor UpperTestDescriptor;
    @Override

    public void execute() {
          String data="";
          String restoreData="";
          String restoreLowerData ="";
          String restoreUpperData ="";
          String UpperStr="";
          String LowerStr="";
          long convert_upperVal=0L;
          long convert_lowerVal=0L;
          MultiSiteString simParam = new MultiSiteString("");
          MultiSiteLong LowersimVal = new MultiSiteLong(-1);
          MultiSiteLong UppersimVal = new MultiSiteLong(-1);
          simParam = context.testProgram().variables().getString(tpVar);

          for(int site:simParam.getActiveSites())
          {
              data = simParam.get(site);

              if(tpVar.equals("lotid"))
              {
                  UpperStr = data.substring(0,3);
                  LowerStr= data.substring(3);
                  //System.out.println(UpperStr+" "+LowerStr);
                  convert_lowerVal=StringToLong(LowerStr);
                  LowersimVal.set(site,convert_lowerVal);
                  restoreLowerData =LongToString(convert_lowerVal,LowerStr.length());

                  convert_upperVal=StringToLong(UpperStr);
                  UppersimVal.set(site,convert_upperVal);
                  restoreUpperData =LongToString(convert_upperVal,UpperStr.length());

                  System.out.println(context.getTestSuiteName()+" Site: "+site+" Original Data: "+ data + " Read Back:" +restoreUpperData+restoreLowerData);
                  //System.out.println(tpVar+" Site: "+site+" Lower 3 Byte Data: "+data+" Convert Value: "+convert_lowerVal +" Read Back: " + restoreLowerData);
                  //System.out.println(tpVar+" Site: "+site+" Upper 3 Byte Data: "+data+" Convert Value: "+convert_upperVal +" Read Back: " + restoreUpperData);

              }
              else
              {
                  convert_lowerVal=StringToLong(data);
                  LowersimVal.set(site,convert_lowerVal);
                  restoreData = LongToString(convert_lowerVal,data.length());
                  System.out.println(context.getTestSuiteName()+" Site: "+site+" Original Data: "+ data + " Read Back:" +restoreData);

                  //System.out.println(tpVar+" Site: "+site+" Data: "+data+" Convert Value: "+convert_lowerVal +" Read Back: " + restoreData);

              }
          }
          //System.out.println(context.getTestSuiteName()+ " lower simVal:"+ LowersimVal);
          LowerTestDescriptor.evaluate(LowersimVal);

          if(tpVar.equals("lotid"))
          {
              //System.out.println(context.getTestSuiteName()+ " Upper simVal:"+ UppersimVal);
              UpperTestDescriptor.evaluate(UppersimVal);
          }
      }

    Long StringToLong(String input)
    {
        long result = 0;
        byte[] bytes = input.getBytes(StandardCharsets.UTF_8);
        // 2. Convert to long using bitwise shifting
        for (byte b : bytes) {
            result = (result << 8) | (b & 0xFF);
        }
        return result;
    }
    String LongToString(long val,int stringLength)
    {
        // 1. Create a byte array to hold the characters
        byte[] bytes = new byte[stringLength];

        // 2. Extract bytes from the long
        long temp = val;
        for (int i = stringLength - 1; i >= 0; i--) {
            // Get the last 8 bits
            bytes[i] = (byte) (temp & 0xFF);
            temp >>= 8;
        }

        // 3. Convert bytes back to String
        String restored = new String(bytes, StandardCharsets.UTF_8);
        //System.out.println("Restored String: " + restored);
        return restored;
    }

}
