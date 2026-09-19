package CustomTML;

import com.advantest.itee.tml.dctml.Continuity.ContinuitySignalInfo;

import xoc.dsa.DeviceSetupFactory;
import xoc.dsa.IDeviceSetup;
import xoc.dsa.ISetupDcVI;
import xoc.dsa.ISetupDcVI.IIforce;
import xoc.dsa.ISetupDcVI.IVmeas;
import xoc.dta.ParameterGroupCollection;
import xoc.dta.TestMethod;
import xoc.dta.UncheckedDTAException;
import xoc.dta.datatypes.MultiSiteBoolean;
import xoc.dta.datatypes.MultiSiteLong;
import xoc.dta.measurement.IMeasurement;
import xoc.dta.resultaccess.IDcVIResults;
import xoc.dta.resultaccess.IDcVIResults.IVmeasResults;
import xoc.dta.testdescriptor.IParametricTestDescriptor;

public class ContiTest extends TestMethod {
    public IMeasurement measurement;
    public String specParameters = "";
    public String dpsSignals = "";
    public double dpsSignalsIclamp = Double.NaN;
    public long wait_time=10L;
    public String signals = "";
    public IParametricTestDescriptor parametricTestDescriptor;
    public MeasureModeType measureMode = MeasureModeType.Serial;
    public ParameterGroupCollection<ContinuitySignalInfo> signalGroup = new ParameterGroupCollection<>();
    public enum MeasureModeType {
        Serial,
        Parallel,
    }
    private boolean isFirstTimeExecution = true;
    public double dpsVrange=Double.NaN;
    public double dpsIrange=Double.NaN;



@Override
public void setup() {
    // 1. Doesn't support to set pattern and operating sequence for measurement in test suite.
    if (isFirstTimeExecution && (measurement.getPatternName() != null || measurement.getOperatingSequenceName() != null)){
        throw new UncheckedDTAException(
                "[Continuity] The pattern name and operating sequence name of measurement can't be set " +
                        "in test suite " + context.getTestSuiteName());
    }
    if(specParameters.isEmpty() && measurement.getSpecificationName()!=null) {
        specParameters = measurement.getSpecificationName();
    }
    try {
        // 3. Create specification and operating sequence files.
        IDeviceSetup deviceSetup = DeviceSetupFactory.createInstance();
        if (!specParameters.isEmpty() && !specParameters.equals(deviceSetup.getSpecificationName())) {
            deviceSetup.importSpec(specParameters);
        }

        // 3.1. Connect DPS before measurement, set the DPS vforce to zero volt to
        // keep it in lowImpedance, and set the current clamp
        if(dpsSignals.equals("")) {
            ISetupDcVI dpsSetup = deviceSetup.addDcVI(dpsSignals);
            dpsSetup.setConnect(true).setDisconnect(true).level().setVforce(0.0);
            dpsSetup.level().setIclamp(dpsSignalsIclamp).setIrange(dpsIrange).setVrange(dpsVrange);
        }
        ISetupDcVI dcvi = deviceSetup.addDcVI(signals);
        dcvi.setConnect(true);
        dcvi.level().setIclamp(50e-3).setIrange(50e-3).setVforce(1.0).setVrange(1.0);
        IIforce iForceAction = dcvi.iforce("iForceAction");
        iForceAction.setForceValue(0).setIrange(0.01).setVclampLow(0).setVclampHigh(0.5);
        IVmeas vMeasAction = dcvi.vmeas("VoltMeas");
        deviceSetup.sequentialBegin();
        {
            deviceSetup.actionCall(iForceAction);
            deviceSetup.actionCall(vMeasAction);
        }
        deviceSetup.sequentialEnd();
        // 4. Link setup info with the measurement.
        measurement.setSetups(deviceSetup);

        // 5. Print generated specification and operating sequence files path to the console.
        //message(20, "[Continuity] The generated specification file path: "
        //        + measurement.getSpecificationName());
        //message(20, "[Continuity] The generated operating sequence file path: "
        //        + measurement.getOperatingSequenceName());

        isFirstTimeExecution = false;

    } catch (Exception e) {
        throw new UncheckedDTAException(
                "[Continuity] Create standard multi-group continuity setup files failed : "
                        + e + " in test suite " + context.getTestSuiteName());
    }
    super.setup();
}
    @Override
    public void execute() {
        MultiSiteBoolean enableWait= new MultiSiteBoolean(true);
        enableWait=context.testProgram().variables().getBooleanOrElse("wait_enable", new MultiSiteBoolean(true));
        MultiSiteLong site_wait = new MultiSiteLong(0);
        site_wait = context.testProgram().variables().getLongOrElse("wait_time", new MultiSiteLong(0));
        int[] sites;

        sites= site_wait.getActiveSites();
        wait_time = site_wait.get(sites[0]);
        if(enableWait.get() == true)
        {
            if(wait_time > 0)
            {
                 try {
                    Thread.sleep(wait_time);
                } catch (InterruptedException e) {
                    e.printStackTrace();
                }
            }
        }
        ExecuteSuiteWait();

        measurement.execute();
        // 1. Release tester hardware.
        this.releaseTester();

        IDcVIResults dcVIResult = null;
        dcVIResult = measurement.dcVI(signals).preserveResults();
        IVmeasResults vmeasActionResult = dcVIResult.vmeas("VoltMeas");
        parametricTestDescriptor.evaluate(vmeasActionResult,0);
    }

    void ExecuteSuiteWait()
    {
        String suiteName = context.getTestSuiteName();
        long _wait=0;
        if (ACSTML.global_variable.Curr_Suites_Delay.DutCnt >0)
        {
            if(ACSTML.global_variable.Curr_Suites_Delay.Hasts(suiteName)== true)
            {
                _wait =ACSTML.global_variable.Curr_Suites_Delay.ts(suiteName).maxDelay();
                if(_wait > 500)
                {
                  System.out.println(suiteName+" wait time: "+_wait+" ms");
                }
                if(_wait >0)
                {
                    try
                    {
                        Thread.sleep(_wait);
                    } catch (InterruptedException e) {
                        e.printStackTrace();
                    }
                }

            }
        }
    }

}
