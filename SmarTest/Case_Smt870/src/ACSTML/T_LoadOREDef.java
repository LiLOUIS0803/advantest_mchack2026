package ACSTML;

import libACS.ORE.Util;
import xoc.dta.TestMethod;

public class T_LoadOREDef extends TestMethod {

    public String Offline_Data_Def_File="offlineData.csv";
    public String PatFailCycle_Def_File="patfaildef.csv";
    public String Offline_delay_Def_File="delay.csv";
    @Override
    public void execute() {
        Util.LoadORESetup(Offline_Data_Def_File, PatFailCycle_Def_File,Offline_delay_Def_File, context);
    }
}
