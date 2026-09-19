package CustomTML;

import xoc.dsa.DeviceSetupFactory;
import xoc.dsa.IDeviceSetup;
import xoc.dta.TestMethod;
import xoc.dta.measurement.IMeasurement;
import xoc.dta.measurement.IOperatingSequenceCallResultsProvider;
import xoc.dta.measurement.IResultProcessingOperation;
import xoc.dta.resultaccess.IDigInOutResults;
import xoc.dta.testdescriptor.ICombinedTestDescriptor;
import xoc.dta.testdescriptor.IFunctionalTestDescriptor;
import xoc.dta.testdescriptor.IScanTestDescriptor;

public class FunctionSmartBurst extends TestMethod {

    public IFunctionalTestDescriptor ftd;
    public IScanTestDescriptor std;

    // You can provide a prefix for the test names. If you don't, the FQN of the current testflow is used.
    public String originalFlow = "";

    public String signals = "";

    // You can provide a string to append to the end of the original test suite name, for example, to indicate a retest.
    public String suitePostfix = "";

    public IMeasurement measurement;
    public String specification = null;
    public String operatingSequence = null;
    public String specParameters = "";
    public String pattern = null;

    private int index = 0;

    @Override
    public void setup() {


        if (specParameters != null && !specParameters.isEmpty()) {
            IDeviceSetup deviceSetup = DeviceSetupFactory.createInstance();
            deviceSetup.importSpec(specification);
            deviceSetup.importSpec(specParameters);
            measurement.setSetups(deviceSetup);

            // Prints the generated specification file path to the console.
            message(20, "[FunctionalTest] measurement specification file name: " + measurement.getSpecificationName());
        }
        if (measurement.getOperatingSequenceName() == null && operatingSequence != null) {
            measurement.setOperatingSequenceName(operatingSequence);
        } else if (measurement.getPatternName() == null && pattern != null) {
            measurement.setPatternName(pattern);
        }
        if (measurement.getSpecificationName() == null && specification != null) {
            measurement.setSpecificationName(specification);
        }


        // TODO Auto-generated method stub
        super.setup();
    }


    @Override
    public void update() {
        // TODO Auto-generated method stub
        measurement.digInOut(signals).result().callPassFail().setEnabled(true);

        super.update();
    }
    @Override
    public void execute() {


        ICombinedTestDescriptor ctd= ICombinedTestDescriptor.create(ftd, std);
        //ICombinedTestDescriptor ctd = xoc.dta.testdescriptor.TestDescriptors.createCombinedTestDescriptor(ftd, std);
        //String CurrTestText= ftd.getTestText();

        index = 0;
        int StartTN= ftd.getTestNumber();
        measurement.setResultProcessingOperation(new IResultProcessingOperation() {

            @Override
            public void process(IOperatingSequenceCallResultsProvider results) {
                String fqn = context.getTestSuiteName() + "." + measurement.getName() + "[" + (index++) + "]";
                //println("Processing results in " + fqn + " " + results.getOperatingSequenceCall().getOperatingSequenceName());
                ftd.setTestText(results.getOperatingSequenceCall().getOperatingSequenceName());
                ftd.setTestNumber(StartTN+(index-1)*10);

                originalFlow = originalFlow.isEmpty()? context.getTestFlowName() : originalFlow;

                String originalSuiteName= context.getTestSuiteName();
                                                                                        // name which should exclude the postfix
                String originalSuiteFQN = originalFlow + "." + originalSuiteName+suitePostfix;
                // We pass the FQN of the original test suite, and then the test name will be appended by the API internally.
                ctd.setTestSuiteName(originalSuiteFQN);

                //datalog
                IDigInOutResults digInOutResults = results.digInOut(signals).preserveResults(ctd);
                ctd.evaluate(digInOutResults);
            }

        });

        measurement.execute();

        //measurement.start();
        //continueFlow();         // To enable the next test suite to start executing
        //measurement.waitDone();
        releaseTester();
    }

}
