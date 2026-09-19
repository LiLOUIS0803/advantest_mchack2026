package ACSTML;

import java.util.Random;

import xoc.dta.TestMethod;
import xoc.dta.datatypes.MultiSiteLong;

public class SetSimResult extends TestMethod {

    public Integer MaxVal=100;
    public String VarName="sim_result";

    @Override
    public void execute() {

        Random rand = new Random();
        Long _val;
        if(MaxVal <=0)
        {
            MaxVal=100;
        }
        MultiSiteLong simResult = new MultiSiteLong(MaxVal);
        simResult = context.testProgram().variables().getLong("sim_result");
        for(int site : simResult.getActiveSites())
        {
            _val=Long.valueOf(rand.nextInt(MaxVal));
            simResult.set(site, _val);
        }
        context.testProgram().variables().set("sim_result", simResult);
//        for(int site:simResult.getActiveSites())
//        {
//            System.out.println(String.valueOf(site)+" "+String.valueOf(simResult.get(site)));
//
//        }
       }
    }
