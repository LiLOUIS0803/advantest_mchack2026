/*******************************************************************************
 * Copyright (c) 2015 Advantest. All rights reserved.
 *
 * Contributors:
 *     Advantest - initial API and implementation
 *******************************************************************************/
package CustomTML;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

import xoc.dsa.DeviceSetupFactory;
import xoc.dsa.IDeviceSetup;
import xoc.dta.ParameterGroup;
import xoc.dta.ParameterGroupCollection;
import xoc.dta.TestMethod;
import xoc.dta.UncheckedDTAException;
import xoc.dta.datatypes.MultiSiteBoolean;
import xoc.dta.measurement.IMeasurement;
import xoc.dta.resultaccess.IDigInOutResults;
import xoc.dta.setupaccess.IParallelGroup;
import xoc.dta.testdescriptor.IFunctionalTestDescriptor;
/**
 * This test method performs a functional test with the setup data specified in the calling test suite. The results can
 * be logged either operating sequence wide or per pattern. <br>
 * To setup a test suite that uses this test method, add the following lines to your main testflow and modify them
 * according to your needs (see the comments and the in-line descriptions): <br>
 *
 * 1) When you want to use an operating sequence:
 *
 * <pre>
 *    suite FunctionalTest calls com.advantest.itee.tml.actml.FunctionalTest {
 *        {@link #specification} = setupRef(&lt;fully qualified name of the specification&gt;);
 *        {@link #operatingSequence} = setupRef(&lt;fully qualified name of the operating sequence&gt;);
 *        specParameters = "The fully qualified name of the additional specification file";    //optional parameter
 *        signals = "Your signals or signal group";
 *
 *        parallelGroup [grp1] = {
 *            parallelGroupName = "The name of a parallel group in the operating sequence";
 *
 *            //The settings below are optional. They will be overwritten by the test table settings,
 *            //if you already have defined them in there.
 *            //The common practice is to set these parameters in the test table.
 *            parallelGroupDescriptor.logLevel = logLevel;
 *            parallelGroupDescriptor.testNumber = testNumber;
 *            parallelGroupDescriptor.testText = "Test Text";
 *            parallelGroupDescriptor.softBinId = softBinNumber;
 *        };
 *
 *        ...
 *
 *        parallelGroup [grpN] = {
 *            parallelGroupName = "The name of a parallel group in the operating sequence";
 *
 *            //The settings below are optional. They will be overwritten by the test table settings,
 *            //if you already have defined them in there.
 *            //The common practice is to set these parameters in the test table.
 *            parallelGroupDescriptor.logLevel = logLevel;
 *            parallelGroupDescriptor.testNumber = testNumber;
 *            parallelGroupDescriptor.testText = "Test Text";
 *            parallelGroupDescriptor.softBinId = softBinNumber;
 *        };
 *
 *        //The settings below are optional. They will be overwritten by the test table settings,
 *        //if you already have defined them in there.
 *        //The common practice is to set these parameters in the test table.
 *        funcTestDescriptor.logLevel = logLevel;
 *        funcTestDescriptor.testNumber = testNumber;
 *        funcTestDescriptor.testText = "Test Text";
 *        funcTestDescriptor.logPerCall = true | false;
 *        funcTestDescriptor.softBinId = softBinNumber;
 *    }
 * </pre>
 *
 * 2) When you want to use a pattern:
 *
 * <pre>
 *    suite FunctionalTest calls com.advantest.itee.tml.actml.FunctionalTest {
 *        {@link #specification} = setupRef(&lt;fully qualified name of the specification&gt;);
 *        {@link #pattern} = setupRef(&lt;fully qualified name of the pattern&gt;);
 *        specParameters = "The fully qualified name of the additional specification file";    //optional parameter
 *        signals = "Your signals or signal groups";
 *
 *        //The settings below are optional. They will be overwritten by the test table settings,
 *        //if you already have defined them in there.
 *        //The common practice is to set these parameters in the test table.
 *        funcTestDescriptor.logLevel = logLevel;
 *        funcTestDescriptor.testNumber = testNumber;
 *        funcTestDescriptor.testText = "Test Text";
 *        funcTestDescriptor.logPerCall = true | false;
 *        funcTestDescriptor.softBinId = softBinNumber;
 *    }
 * </pre>
 *
 * <b>Note:</b> You can specify either a pattern or an operating sequence, not both.
 * <p>
 * Replace <code>&lt;The fully qualified name ...&gt;</code> by the fully qualified name of your corresponding setup
 * data.
 * <p>
 *
 * @since 8.0.3
 * @see "FunctionalTest detailed descriptions in TDC (Topic 255790)"
 */
public class FunctionalTest extends TestMethod {

    /**
     * (Mandatory)<br>
     * Specifies the specification file to use for this measurement. This specification file should contain the signals
     * or signal group definitions and all the instrument settings and setups (level and timing sets, wavetables,
     * actions) that are required to perform this measurement.
     *
     * @since 8.2.4
     */
    public String specification = null;

    /**
     * (Optional)<br>
     * Specifies the pattern file to use for preconditioning the DUT input signals to the desired state before the
     * measurement is performed.
     *
     * @since 8.2.4
     */
    public String pattern = null;

    /**
     * (Optional)<br>
     * Specifies the operating sequence file to use for preconditioning the DUT input signals to the desired state
     * before the measurement is performed.
     *
     * @since 8.2.4
     */
    public String operatingSequence = null;

    /**
     * Defines the measurement object associated with this test method.<br>
     * Please do not directly assign setup data to this measurement in your test suite because it will become private in
     * a future SmarTest version.<br>
     * Instead, you should assign specification to {@link #specification} and assign pattern to {@link #pattern} or
     * operating sequence to {@link #operatingSequence} in your test suite, like below:
     *
     * <pre>
     *     {@link #specification} = setupRef(&lt;fully qualified name of the specification&gt;);
     *     {@link #operatingSequence} = setupRef(&lt;fully qualified name of the operating sequence&gt;);
     * </pre>
     *
     * @since 8.0.3
     */
    public IMeasurement measurement;

    /**
     * (Optional)<br>
     * Used for evaluating the operating sequence results. You can turn on the results logging per pattern by specifying
     * "funcTestDescriptor.setLogPerCall(true)".
     *
     * @since 8.0.3
     */
    public IFunctionalTestDescriptor funcTestDescriptor;
    //public IParametricTestDescriptor paramtricTestDescriptor;

    /**
     * (Optional)<br>
     * Declares the field that is used in the test suite to access the "parallelGroup" parameter group.
     *
     * @since 8.0.4
     */
    public ParameterGroupCollection<ParallelGroupInfo> parallelGroup = new ParameterGroupCollection<>();

    /**
     * (Optional)<br>
     * Specifies the specification file to import for overwriting the timing and level variables that are defined in the
     * specification file assigned to the {@link #measurement} object.
     *
     * @since 8.0.4
     */
    public String specParameters = "";

    /**
     * (Mandatory)<br>
     * Specifies the signals for which the results are logged. If this parameter is empty, test method will get signals
     * from current pattern or operating sequence as the default signals, which will cost some performance.
     *
     * @since 8.0.3
     */
    public String signals = "";

    /**
     * Specifies the maximum log level among test descriptors.
     *
     * @since 8.0.4
     */
    private int maxLogLevel = 0;

    public long wait_time=0L;

    /**
     * Specifies a list to store the test descriptors.
     *
     * @since 8.0.4
     */
    private final List<IFunctionalTestDescriptor> testDescriptorList = new ArrayList<>();

    @Override
    public void setup() {
        // Make sure there is no duplicated logging for pattern results.
        if (funcTestDescriptor.getLogLevel() != 0 && funcTestDescriptor.isLogPerCall() && parallelGroup.size() > 0) {
            throw new UncheckedDTAException(
                    "[FunctionalTest] 'logPerCall' set to true and parallel group size greater than zero leads to "
                            + "duplicated logging in test suite " + context.getTestSuiteName());
        }

        if(specification == null && measurement.getSpecificationName() == null) {
            throw new UncheckedDTAException(
                    "[FunctionalTest] Please set 'specification' in test suite " + context.getTestSuiteName());
        }

        if (specification == null) {
            specification = measurement.getSpecificationName();
        }
        if (pattern == null && measurement.getPatternName() != null) {
            pattern = measurement.getPatternName();
        }
        if (operatingSequence == null && measurement.getOperatingSequenceName() != null) {
            operatingSequence = measurement.getOperatingSequenceName();
        }

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
    }

    @Override
    public void update() {

        testDescriptorList.clear();

        // 1. Get signals from pattern or operating sequence as default signals, when 'signals' is empty.
        if (signals.isEmpty()) {
            Set<String> signalsSet = null;

            if (pattern != null) {
                signalsSet = context.pattern(pattern).getSignals();
            } else {
                signalsSet = measurement.operatingSequence().getDigitalSignals();
            }

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

        // 2. Enables the label pass fail flag, when the results are to be logged per pattern.
        if (funcTestDescriptor.isLogPerCall() || parallelGroup.size() > 0) {
            measurement.digInOut(signals).result().callPassFail().setEnabled(true);
        }

        maxLogLevel = funcTestDescriptor.getLogLevel();

        testDescriptorList.add(funcTestDescriptor);

        for (ParallelGroupInfo parallelGroupInfo : parallelGroup.values()) {
            maxLogLevel = maxLogLevel > parallelGroupInfo.parallelGroupDescriptor.getLogLevel() ? maxLogLevel
                    : parallelGroupInfo.parallelGroupDescriptor.getLogLevel();

            // 2.1. Sets the "logPerCall" to true, as parallel group always log per pattern results.
            parallelGroupInfo.parallelGroupDescriptor.setLogPerCall(true);

            testDescriptorList.add(parallelGroupInfo.parallelGroupDescriptor);
        }

        // 3. Enables the cycle pass fail flag, when the maximum log level is 30 or higher.
        if (maxLogLevel >= 30) {
            measurement.digInOut(signals).result().cyclePassFail().setEnabled(true);
        }
    }

    @Override
    public void execute() {

        //PrintByPassPat();
        measurement.execute();

        // 1. Preserves the test results.
        IDigInOutResults results = measurement.digInOut(signals)
                .preserveResults(testDescriptorList.toArray(new IFunctionalTestDescriptor[testDescriptorList.size()]));

        // 2. Releases the tester.
        releaseTester();

        // 3. Data log the results.
        funcTestDescriptor.evaluate(results);
        //paramtricTestDescriptor.evaluate(results);
        // 4. Data log per pattern results in each parallel group.
        for (ParallelGroupInfo parallelGroupInfo : parallelGroup.values()) {
            parallelGroupInfo.parallelGroupDescriptor
                    .evaluate(results.parallel(parallelGroupInfo.parallelGroupName).pattern(""));
        }

    }

    /**
     * Adds the parameter group sub-class to this test method.
     *
     * @since 8.0.4
     */
    public static class ParallelGroupInfo extends ParameterGroup {

        /**
         * Used to evaluate the pattern results in the current parallel group.
         *
         * @since 8.0.4
         */
        public IFunctionalTestDescriptor parallelGroupDescriptor;

        /**
         * Specifies the name of the top level parallel group in the operating sequence.
         *
         * @since 8.0.4
         */
        public String parallelGroupName;

    }
    private void PrintByPassPat()
    {
        MultiSiteBoolean bypassFlag = new MultiSiteBoolean(true);

        List<IParallelGroup> paraGroups = measurement.operatingSequence().getParallelGroups();

        for (IParallelGroup iParallelGroup : paraGroups) {
            String iParallelGroupName = iParallelGroup.getName();
            println("Debug Info: iParallelGroupName = " + iParallelGroupName);
            if(iParallelGroupName.equals("MP_P2"))
            {
               iParallelGroup.setBypass(bypassFlag);
            }

        }
    }
}
