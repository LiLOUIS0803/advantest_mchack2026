package CustomTML;

import java.util.List;
import java.util.Map.Entry;

import xoc.dta.TestMethod;
import xoc.dta.datatypes.MultiSiteBoolean;
import xoc.dta.measurement.IMeasurement;
import xoc.dta.setupaccess.IOperatingSequenceCall;
import xoc.dta.setupaccess.IParallelGroup;

public class PatternBypass extends TestMethod {

    public String pattern=null;
    public String targetpgrp=null;
    public Boolean bypassed=true;

    @Override
    public void execute() {
        // TODO Auto-generated method stub
        IMeasurement TargetMeas;

        MultiSiteBoolean bypassFlag = new MultiSiteBoolean(bypassed);
        println(context.getTestSuiteName()+ "  set pattern bypass to "+bypassed);
        for (Entry<String, IMeasurement> mapRow : context.testProgram().getMeasurements("**"+pattern+"**").entrySet()) {

            println("Fully qualified name: " + mapRow.getKey());
            //println("Measurement name: " + mapRow.getValue().getName());
            TargetMeas=mapRow.getValue();
            List<IOperatingSequenceCall> OpCallList= TargetMeas.operatingSequence().getOperatingSequenceCalls();

            if(OpCallList.size()>0)
            {
                for(IOperatingSequenceCall Opcall : OpCallList)
                {
                    String SeqName=Opcall.getOperatingSequenceName();
                     //println("OpCallName: "+Opcall.getOperatingSequenceName());
                    if(SeqName.contains(targetpgrp))
                    {
                        Opcall.setBypass(bypassFlag);
                        println("Bypass Sequence "+SeqName+" isBypass: "+Opcall.getBypass());
                    }
                }
            }
            else
            {
                List<IParallelGroup> paraGroups = TargetMeas.operatingSequence().getParallelGroups();
                for (IParallelGroup iParallelGroup : paraGroups) {
                    String iParallelGroupName = iParallelGroup.getName();
                    //println("Debug Info: iParallelGroupName = " + iParallelGroupName);
                    if(iParallelGroupName.equals(targetpgrp))
                    {
                        iParallelGroup.setBypass(bypassFlag);
                        println("Parallel Group "+iParallelGroupName+" isBypass: "+iParallelGroup.getBypass());
                    }
                }
            }


       }
    }

}
