package ACSTML;

import java.util.ArrayList;

import libACS.ORE.Util;
import libACS.ORE.dutInfo;
import xoc.dta.TestMethod;
import xoc.dta.datatypes.MultiSiteLong;
import xoc.dta.datatypes.MultiSiteString;

public class T_ORE_Build extends TestMethod {

    public Integer debug=0;
    @Override
    public void execute() {
        Util.ActivateORESetup(context,debug);

        global_variable.Curr_Suites_Delay = Util.FetchSuiteDelays();

        String stage ="ft";
        MultiSiteString tmpVal = context.testProgram().variables().getStringOrElse("stage",new MultiSiteString(""));
        int[] sites = tmpVal.getActiveSites();
        stage = tmpVal.get(sites[0]).toLowerCase().strip();


        MultiSiteString test_cod = context.testProgram().variables().getStringOrElse("STDF.TEST_COD",new MultiSiteString(""));
        //sites = test_cod.getActiveSites();
        String updateStage = test_cod.get(sites[0]).toLowerCase().strip();

        if(!updateStage.equals(""))
        {
            stage= updateStage;
        }
        if(stage.toLowerCase().contains("ft"))
        {
            System.out.println("Stage is Final Test");
            ArrayList<dutInfo> simduts = Util.FetchSimDuts();
            int[] activate_sites;
            int i;
            MultiSiteLong xCoords= new MultiSiteLong(-1);
            MultiSiteLong yCoords= new MultiSiteLong(-1);
            MultiSiteString lotids= new MultiSiteString(-1);
            MultiSiteString waferids= new MultiSiteString(-1);
            activate_sites = xCoords.getActiveSites();

            for(i=0;i< activate_sites.length;i++)
            {
                xCoords.set(activate_sites[i],Integer.parseInt(simduts.get(i).X));
                yCoords.set(activate_sites[i],Integer.parseInt(simduts.get(i).Y));
                lotids.set(activate_sites[i],simduts.get(i).LotID);
                waferids.set(activate_sites[i],simduts.get(i).WaferID);
            }
            context.testProgram().variables().set("STDF.X_COORD", xCoords);
            context.testProgram().variables().set("STDF.Y_COORD", yCoords);
            context.testProgram().variables().set("lotid", lotids);
            context.testProgram().variables().set("waferid", waferids);
        }
        else
        {
            System.out.print("Stage is Wafer Sort");
        }
    }
}
