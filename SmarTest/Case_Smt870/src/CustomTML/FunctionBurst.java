/*******************************************************************************
 * Copyright (c) 2015 Advantest. All rights reserved.
 *
 * Contributors:
 *     Advantest - initial API and implementation
 *******************************************************************************/
package CustomTML;

import java.util.Iterator;
import java.util.List;
import java.util.Set;

import xoc.dsa.DeviceSetupUncheckedException;
import xoc.dsa.DeviceSetupUtils;
import xoc.dsa.IDeviceSetup;
import xoc.dta.ParameterGroup;
import xoc.dta.ParameterGroupCollection;
import xoc.dta.TestMethod;
import xoc.dta.UncheckedDTAException;
import xoc.dta.measurement.IMeasurement;
import xoc.dta.resultaccess.IDigInOutResults;
import xoc.dta.testdescriptor.IFunctionalTestDescriptor;

/**
 * This test method performs a functional burst test with the setup data specified in the calling test suite.
 * The results can be logged either operating sequence wide or per pattern.<br>
 * To setup a test suite that uses this test method, add the following lines to your main
 * testflow and modify them according to your needs (see the comments and the in-line
 * descriptions): <br>
 *
 * <pre>
 *    suite FunctionalBurst calls com.advantest.itee.tml.actml.FunctionalBurst {
 *        specificationName = "fully qualified name of specification";
 *        specParameters = "fully qualified name of additional specification";    //optional parameter
 *        signals = "signal group";
 *
 *        patternAndOpSeqGroup [grp1] = {
 *            appendPatternList = #["fully qualified name of pattern1",
 *                                  "fully qualified name of pattern2"];
 *            bypassablePatternList = true;
 *        };
 *
 *        ...
 *
 *        patternAndOpSeqGroup [grpN] = {
 *            appendOperatingSequence = "fully qualified name of operating sequence";
 *        };
 *
 *        //Below setting are optional,which will be overwritten by test table setting,
 *        //if already define them in test table.
 *        //Common practice is to set in test table.
 *        funcTestDescriptor.logLevel = logLevel;
 *        funcTestDescriptor.testNumber = testNumber;
 *        funcTestDescriptor.testText = "Test Text";
 *        funcTestDescriptor.logPerCall = true | false ;
 *        funcTestDescriptor.softBinId = softBinNumber;
 *    }
 * </pre>
 *
 * @since 8.0.5
 * @see "FunctionalBurst detailed descriptions in TDC (Topic 255783)"
 */
public class FunctionBurst extends TestMethod {

    /**
     * (Optional)<br>
     * Used for evaluating the operating sequence results. You can turn on the results
     * logging per pattern by specifying "funcTestDescriptor.setLogPerCall(true)".
     *
     * @since 8.0.5
     */
    public IFunctionalTestDescriptor funcTestDescriptor;

    /**
     * (Mandatory)<br>
     * Declares the field that is used in the test suite to access the
     * "patternAndOpSeqGroup" parameter group.
     *
     * @since 8.0.5
     */
    public ParameterGroupCollection<PatternAndOpSeqInfo > patternAndOpSeqGroup = new ParameterGroupCollection<>();

    /**
     * (Mandatory)<br>
     * Specifies the specification file to use for this measurement.
     * This specification file should contain the signals or signal group definitions and
     * all the instrument settings and setups (level and timing sets, wavetables, actions)
     * that are required to perform this measurement.
     *
     * @since 8.0.5
     */
    public String specificationName = "";

    /**
     * (Optional)<br>
     * Specifies an additional specification file for overwriting the timing and level
     * variables of the specification file specified with {@link #specificationName}.
     *
     * @since 8.0.5
     */
    public String specParameters = "";

    /**
     * (Mandatory)<br>
     * Specifies the signals for which the results are logged.
     * If the signals is empty, test method will get signals from current
     * operating sequence as the default signals, which will cost some performance.
     *
     * @since 8.0.5
     */
    public String signals = "";

    /**
     * Defines the measurement object associated with this test method.
     *
     * @since 8.0.5
     */
    private IMeasurement measurement;

    @Override
    public void setup() {
        if (patternAndOpSeqGroup.size() == 0 || specificationName.trim().isEmpty()) {
            throw new UncheckedDTAException("[FunctionalBurst] Please input valid value for parameters: " +
                    "'patternAndOpSeqGroup', 'specificationName' in test suite " + context.getTestSuiteName());
        }

        try {
            // 1. Pass the specification file to measurement.
            measurement.setSpecificationName(specificationName);

            // 2. Optional specification file for overwriting timing and level defined in measurement specification file.
            IDeviceSetup deviceSetup = DeviceSetupUtils.setSpecParameters(measurement, specParameters);

            if (measurement.getSpecificationName() != null &&
                    !measurement.getSpecificationName().equals(deviceSetup.getSpecificationName())) {
                deviceSetup.importSpec(measurement.getSpecificationName());
            }

            // 3. Create the operating sequence file and burst the pattern in sequential.
            for (PatternAndOpSeqInfo  patternAndOpSeqInfo : patternAndOpSeqGroup.values()) {
                if (patternAndOpSeqInfo.appendPatternList != null && !patternAndOpSeqInfo.appendPatternList.isEmpty()
                        && !patternAndOpSeqInfo.appendOperatingSequence.isEmpty()) {
                    throw new UncheckedDTAException("[FunctionalBurst] Either 'appendPatternList' or 'appendOperatingSequence' is valid," +
                            " but not both in group [" + patternAndOpSeqInfo.getId() + "]");
                }

                if (patternAndOpSeqInfo.bypassablePatternList && !patternAndOpSeqInfo.appendOperatingSequence.isEmpty()) {
                    throw new UncheckedDTAException("[FunctionalBurst] When 'appendOperatingSequence' has valid value," +
                            " 'bypassablePatternName' must be false in group [" + patternAndOpSeqInfo.getId() + "]");
                }

                // 3.1. Call patterns sequential,set set it bypassble according parameters.
                if (patternAndOpSeqInfo.appendPatternList != null && !patternAndOpSeqInfo.appendPatternList.isEmpty()) {
                    deviceSetup.parallelBegin();
                    {
                        if (patternAndOpSeqInfo.bypassablePatternList) {
                            deviceSetup.setBypassable();
                        }

                        if (!patternAndOpSeqInfo.isExecPatternsPar) {
                            deviceSetup.sequentialBegin();
                        }

                        {
                            for (String patternName : patternAndOpSeqInfo.appendPatternList){
                                deviceSetup.patternCall(patternName);
                            }
                        }

                        if (!patternAndOpSeqInfo.isExecPatternsPar) {
                            deviceSetup.sequentialEnd();
                        }
                    }
                    deviceSetup.parallelEnd();
                }

                // 3.2. Call operating sequence files.
                if (!patternAndOpSeqInfo.appendOperatingSequence.isEmpty()) {
                    deviceSetup.operatingSequenceCall(patternAndOpSeqInfo.appendOperatingSequence);
                }
            }

            // 4. Link setup info with the measurement.
            measurement.setSetups(deviceSetup);

            // 5. Print generated specification and operating sequence files path to the console.
            message(20, "[FunctionalBurst] measurement specification file name: " + measurement.getSpecificationName());
            message(20, "[FunctionalBurst] measurement operating sequence file name: " + measurement.getOperatingSequenceName());

        } catch (DeviceSetupUncheckedException e) {
            throw new UncheckedDTAException("[FunctionalBurst] Create functional burst setup files failed : " + e
                    + " in test suite: " + context.getTestSuiteName());
        }

    }

    @Override
    public void update() {
        // 1. Get signals from operating sequence as default signals, when scan signals is empty.
        if (signals.isEmpty()) {

            Set<String> signalsSet = measurement.operatingSequence().getDigitalSignals();

            if (signalsSet != null && signalsSet.size() > 0) {
                StringBuffer signalsSb = new StringBuffer("");
                Iterator<String> it = signalsSet.iterator();
                signalsSb.append(it.next());
                while (it.hasNext()) {
                    signalsSb.append("+").append(it.next());
                }
                signals = signalsSb.toString();
            }
        }

        // 2. Enable the label pass fail flag, when per pattern results are to be logged.
        if(funcTestDescriptor.isLogPerCall()) {
            measurement.digInOut(signals).result().callPassFail().setEnabled(true);
        }

        // 3. Enable cycle pass fail flag, when max log level is 30 or higher.
        if (funcTestDescriptor.getLogLevel() >= 30) {
            measurement.digInOut(signals).result().cyclePassFail().setEnabled(true);
        }
    }

    @Override
    public void execute() {
        measurement.execute();

        // 1. Preserve the results.
        IDigInOutResults results = measurement.digInOut(signals).preserveResults(funcTestDescriptor);

        // 2. Release the tester.
        releaseTester();

        // 3. Data log results.
        funcTestDescriptor.evaluate(results);

    }


    /**
     * Parameter group for the pattern list or operating sequence to be measured.
     *
     * @since 8.0.5
     */
    public static class PatternAndOpSeqInfo  extends ParameterGroup {

        /**
         * Operating sequence name of this group.
         *
         * @since 8.0.5
         */
        public String appendOperatingSequence = "";

        /**
         * Pattern list of this group.
         *
         * @since 8.0.5
         */
        public List<String> appendPatternList;

        /**
         * Enable/disable bypassable patterns in {@link #appendPatternList}.
         *
         * @since 8.0.5
         */
        public boolean bypassablePatternList = false;

        /**
         * Execute patterns in {@link #appendPatternList} parallel or sequential.
         * Default is parallel.
         *
         * @since 8.0.5
         */
        public boolean isExecPatternsPar = true;
    }
}

