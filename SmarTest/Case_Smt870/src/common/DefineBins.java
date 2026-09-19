package common;

import xoc.dta.TestMethod;
import xoc.dta.binning.IBinTable;
import xoc.dta.binning.IBinning.Color;
import xoc.dta.binning.IBinning.ResultType;

/**
 * An example test method using test descriptor
 */
public class DefineBins extends TestMethod {

    @Override
    public void execute() {
        IBinTable binTable = context.binning().binTable();
        binTable.clear();


        binTable.addHardBin(1, "passed", ResultType.PASS);
        binTable.addHardBin(2, "bin2", ResultType.FAIL);
        binTable.addHardBin(3, "bin3", ResultType.FAIL);
        binTable.addHardBin(4, "bin4", ResultType.FAIL);
        binTable.addHardBin(5, "bin5", ResultType.FAIL);
        binTable.addHardBin(6, "bin6", ResultType.FAIL);
        binTable.addHardBin(7, "bin7", ResultType.FAIL);
        binTable.addHardBin(8, "bin8", ResultType.FAIL);
        binTable.addHardBin(9, "bin9", ResultType.FAIL);
        binTable.addHardBin(10, "bin10", ResultType.FAIL);
        binTable.addHardBin(11, "bin11", ResultType.FAIL);
        binTable.addHardBin(12, "bin12", ResultType.FAIL);
        binTable.addHardBin(13, "bin13", ResultType.FAIL);
        binTable.addHardBin(14, "bin14", ResultType.FAIL);
        binTable.addHardBin(15, "bin15", ResultType.FAIL);
        binTable.addHardBin(16, "bin16", ResultType.FAIL);
        binTable.addHardBin(17, "bin17", ResultType.FAIL);
        binTable.addHardBin(18, "bin18", ResultType.FAIL);
        binTable.addHardBin(19, "bin19", ResultType.FAIL);
        binTable.addHardBin(20, "bin20", ResultType.FAIL);
        binTable.addHardBin(21, "bin21", ResultType.FAIL);
        binTable.addHardBin(22, "bin22", ResultType.FAIL);
        binTable.addHardBin(23, "bin23", ResultType.FAIL);
        binTable.addHardBin(24, "bin24", ResultType.FAIL);
        binTable.addHardBin(25, "bin25", ResultType.FAIL);
        binTable.addHardBin(26, "bin26", ResultType.FAIL);
        binTable.addHardBin(27, "bin27", ResultType.FAIL);
        binTable.addHardBin(28, "bin28", ResultType.FAIL);
        binTable.addHardBin(29, "bin29", ResultType.FAIL);
        binTable.addHardBin(30, "bin30", ResultType.FAIL);
        binTable.addHardBin(31, "bin31", ResultType.FAIL);
        binTable.addHardBin(32, "bin32", ResultType.FAIL);


        binTable.addSoftBin(1, 1, "passed", ResultType.PASS, 0, Color.GREEN);
        binTable.addSoftBin(2, 2, "bin2", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(3, 3, "bin3", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(4, 4, "bin4", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(5, 5, "bin5", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(6, 6, "bin6", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(7, 7, "bin7", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(8, 8, "bin8", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(9, 9, "bin9", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(10, 10, "bin10", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(11, 11, "bin11", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(12, 12, "bin12", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(13, 13, "bin13", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(14, 14, "bin14", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(15, 15, "bin15", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(16, 16, "bin16", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(17, 17, "bin17", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(18, 18, "bin18", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(19, 19, "bin19", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(20, 20, "bin20", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(21, 21, "bin21", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(22, 22, "bin22", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(23, 23, "bin23", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(24, 24, "bin24", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(25, 25, "bin25", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(26, 26, "bin26", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(27, 27, "bin27", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(28, 28, "bin28", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(29, 29, "bin29", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(30, 30, "bin30", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(31, 31, "bin31", ResultType.FAIL, 0, Color.RED);
        binTable.addSoftBin(32, 32, "bin32", ResultType.FAIL, 0, Color.RED);

    }
}
