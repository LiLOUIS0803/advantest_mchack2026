package CustomTML;

/*******************************************************************************
 * Copyright (c) 2015 Advantest. All rights reserved.
 *
 * Contributors:
 *     Advantest - initial API and implementation
 *******************************************************************************/

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Set;

import com.advantest.itee.tml.scan.ScanReportToFile;

import xoc.dsa.DeviceSetupFactory;
import xoc.dsa.IDeviceSetup;
import xoc.dta.ParameterGroup;
import xoc.dta.ParameterGroupCollection;
import xoc.dta.TestMethod;
import xoc.dta.UncheckedDTAException;
import xoc.dta.measurement.IMeasurement;
import xoc.dta.resultaccess.IDigInOutResults;
import xoc.dta.testdescriptor.IScanTestDescriptor;
import xoc.dta.workspace.IWorkspace;

/**
 * This test method performs a scan test with the setup data specified in the calling test suite. It can log the results
 * either operating sequence wide or per pattern. <br>
 * To setup a test suite that uses this test method, add the following lines to your main testflow and adapt or modify
 * them according to your needs (see the comments and the in-line descriptions): <br>
 * <ol>
 *
 * <li>When you want to use an operating sequence:
 *
 * <pre>
 *    suite ScanTest calls com.advantest.itee.tml.scan.ScanTest {
 *        {@link #specification} = setupRef(&lt;fully qualified name of the specification&gt;);
 *        {@link #operatingSequence} = setupRef(&lt;fully qualified name of the operating sequence&gt;);
 *        specParameters = "fully qualified name of additional specification";    //optional parameter
 *        isReportToFile = false; //optional parameter
 *        scanSignals = "signalsName";
 *
 *        parallelGroup [grp1] = {
 *            parallelGroupName = "parallel group name in operating sequence";
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
 *            parallelGroupName = "parallel group name in operating sequence";
 *
 *            //The settings below are optional. They will be overwritten by the test table settings,
 *            //if you already have defined them in there.
 *            //The common practice is to set these parameters in the test table
 *            parallelGroupDescriptor.logLevel = logLevel;
 *            parallelGroupDescriptor.testNumber = testNumber;
 *            parallelGroupDescriptor.testText = "Test Text";
 *            parallelGroupDescriptor.softBinId = softBinNumber;
 *        };
 *
 *        //The settings below are optional. They will be overwritten by the test table settings,
 *        //if you already have defined them in there.
 *        //The common practice is to set these parameters in the test table.
 *        scanTestDescriptor.logLevel = logLevel;
 *        scanTestDescriptor.testNumber = testNumber;
 *        scanTestDescriptor.testText = "Test Text";
 *        scanTestDescriptor.logPerCall = true | false;
 *        scanTestDescriptor.softBinId = softBinNumber;
 *    }
 * </pre>
 *
 * </li>
 *
 * <li>When you want to use a pattern:
 *
 * <pre>
 *    suite ScanTest calls com.advantest.itee.tml.scan.ScanTest {
 *        {@link #specification} = setupRef(&lt;fully qualified name of the specification&gt;);
 *        {@link #pattern} = setupRef(&lt;fully qualified name of the pattern&gt;);
 *        specParameters = "fully qualified name of additional specification";    //optional parameter
 *        isReportToFile = false; //optional parameter
 *        scanSignals = "signalsName";
 *
 *        //The settings below are optional. They will be overwritten by the test table settings,
 *        //if you already have defined them in there.
 *        //The common practice is to set these parameters in the test table.
 *        scanTestDescriptor.logLevel = logLevel;
 *        scanTestDescriptor.testNumber = testNumber;
 *        scanTestDescriptor.testText = "Test Text";
 *        scanTestDescriptor.logPerCall = true | false;
 *        scanTestDescriptor.softBinId = softBinNumber;
 *    }
 * </pre>
 *
 * </li>
 * </ol>
 *
 * <b>Note:</b> Specify either a pattern or an operating sequence, not both.
 * <p>
 * Replace the <code>&lt;fully qualified name&gt;</code> by the fully qualified name of your corresponding setup data.
 * <p>
 *
 * @since 8.0.3
 * @see "ScanTest detailed descriptions in TDC (Topic 255804)"
 */
public class ScanTest extends TestMethod {

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
     * Used to evaluate the operating sequence results which by default are per pattern. Note that you can turn off per
     * pattern result logging through specifying "scanTestDescriptor.setLogPerCall(false)".
     *
     * @since 8.0.3
     */
    public IScanTestDescriptor scanTestDescriptor;

    /**
     * (Optional)<br>
     * Declares the field that is used in the test suite to access the "parallelGroup" parameter group.
     *
     * @since 8.0.4
     */
    public ParameterGroupCollection<com.advantest.itee.tml.scan.ScanTest.ParallelGroupInfo> parallelGroup = new ParameterGroupCollection<>();

    /**
     * (Optional)<br>
     * Specifies an additional specification file for overwriting the timing and level variables of the specification
     * file specified with {@link #measurement}.
     *
     * @since 8.0.4
     */
    public String specParameters = "";

    /**
     * (Mandatory)<br>
     * Specifies the DUT signals based on which the results are logged. If the scanSignals is empty, test method will
     * get signals from current pattern or operating sequence as the default signals, which will cost some performance.
     *
     * @since 8.0.3
     */
    public String scanSignals = "";

    /**
     * (Optional)<br>
     * Outputs the failed results to a text file, default is false.
     *
     * @since 8.0.4
     */
    public boolean isReportToFile = false;

    /**
     * Specifies the maximum log level among the test descriptors.
     *
     * @since 8.0.4
     */
    private int maxLogLevel = 0;

    /**
     * Specifies the maximum failed cycles among the test descriptors.
     */
    public int maxFailedCycles = 10000;

    /**
     * The list to store the test descriptors.
     *
     * @since 8.0.4
     */
    private final List<IScanTestDescriptor> testDescriptorList = new ArrayList<>();

    @Override
    public void setup() {
        // Make sure no duplicated logging for pattern results.
        if (scanTestDescriptor.getLogLevel() != 0 && scanTestDescriptor.isLogPerCall() && parallelGroup.size() > 0) {
            throw new UncheckedDTAException(
                    "[ScanTest] 'logPerCall' set to true and parallel group size greater than zero leads to "
                            + "duplicated logging in test suite " + context.getTestSuiteName());
        }

        if(specification == null && measurement.getSpecificationName() == null) {
            throw new UncheckedDTAException(
                    "[ScanTest] Please set 'specification' in test suite " + context.getTestSuiteName());
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
            message(20, "[ScanTest] measurement specification file name: " + measurement.getSpecificationName());
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

        // 1. Get signals from pattern or operating sequence as default signals, when scan signals is empty.
        if (scanSignals.isEmpty()) {
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
                scanSignals = signalsSb.toString();
            }
        }

        // 2. Enable the pattern pass fail flag, when per pattern results are to be logged.
        if (scanTestDescriptor.isLogPerCall() || parallelGroup.size() > 0) {
            measurement.digInOut(scanSignals).result().callPassFail().setEnabled(true);
        }

        maxLogLevel = scanTestDescriptor.getLogLevel();
        testDescriptorList.add(scanTestDescriptor);

        for (com.advantest.itee.tml.scan.ScanTest.ParallelGroupInfo parallelGroupInfo : parallelGroup.values()) {
            maxLogLevel = maxLogLevel > parallelGroupInfo.parallelGroupDescriptor.getLogLevel() ? maxLogLevel
                    : parallelGroupInfo.parallelGroupDescriptor.getLogLevel();

            // 2.1. Set 'logPerCall' to true, as parallel group always log per pattern
            // results.
            parallelGroupInfo.parallelGroupDescriptor.setLogPerCall(true);

            testDescriptorList.add(parallelGroupInfo.parallelGroupDescriptor);
        }

        // 3. Enable cycle pass fail flag, when max log level is 30 or higher.
        if (maxLogLevel >= 30) {
            measurement.digInOut(scanSignals).result().cyclePassFail().setEnabled(true);
            measurement.digInOut(scanSignals).result().cyclePassFail().setMaxFailedCycles(maxFailedCycles);
        }
    }

    @Override
    public void execute() {
        measurement.execute();

        // 1. Preserve the test results.
        IDigInOutResults results = measurement.digInOut(scanSignals)
                .preserveResults(testDescriptorList.toArray(new IScanTestDescriptor[testDescriptorList.size()]));

        // 2. Release the tester.
        releaseTester();

        // 3. Log the results.
        scanTestDescriptor.evaluate(results);

        // 4. Log the results for each parallel group with per pattern.
        for (com.advantest.itee.tml.scan.ScanTest.ParallelGroupInfo parallelGroupInfo : parallelGroup.values()) {
            parallelGroupInfo.parallelGroupDescriptor
                    .evaluate(results.parallel(parallelGroupInfo.parallelGroupName).pattern(""));
        }

        // 5. Dump the results to text file.
        if (isReportToFile) {
            reportToFile(results);
        }

    }

    /**
     * Adds the parameter group sub-class to this test method.
     *
     * @since 8.0.4
     */
    public static class ParallelGroupInfo extends ParameterGroup {

        /**
         * Adds the parametric test descriptor sub-class to this test method. This parametric test descriptor is used to
         * evaluate the test suite results.
         *
         * @since 8.0.4
         */
        public IScanTestDescriptor parallelGroupDescriptor;

        /**
         * Specifies the name of the top level parallel group in the operating sequence.
         *
         * @since 8.0.4
         */
        public String parallelGroupName;

    }

    private void reportToFile(IDigInOutResults results) {
        String logPath = IWorkspace.getActiveProjectPath() + "/report/scan/";
        String patternOpSeqName = pattern != null ? pattern : operatingSequence;

        ScanReportToFile reportToFile = new ScanReportToFile();

        reportToFile.getSettingData().setDumpFilePath(logPath).setTestSuiteName(context.getTestSuiteName())
                .setPatternOrOpSeqName(patternOpSeqName).setOpSeqPerPattern(scanTestDescriptor.isLogPerCall())
                .setOpSeqLogLevel(scanTestDescriptor.getLogLevel()).setParallelGroup(parallelGroup)
                .setDigInOutResults(results).setSites(context.getActiveSites());

        reportToFile.dumpFile();
    }
}

