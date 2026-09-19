package ACSTML;

import xoc.dta.TestMethod;
import xoc.dta.datatypes.MultiSiteString;

public class EngSTDFInit extends TestMethod {

    @Override
    public void execute() {
        // TODO Auto-generated method stub
        MultiSiteString strVal = new MultiSiteString("FT");
        context.testProgram().variables().set("STDF.TEST_COD", strVal);

        strVal = new MultiSiteString("A3847573");
        context.testProgram().variables().set("STDF.LOT_ID", strVal);

        strVal = new MultiSiteString("v1.0.0");
        context.testProgram().variables().set("STDF.JOB_REV", strVal);

        strVal = new MultiSiteString("testUser");
        context.testProgram().variables().set("STDF.OPER_NAM", strVal);

        strVal = new MultiSiteString("B123566");
        context.testProgram().variables().set("STDF.LOAD_ID", strVal);

        strVal = new MultiSiteString("F12345");
        context.testProgram().variables().set("STDF.PART_TYP", strVal);

    }
}
