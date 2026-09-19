package ACSTML;


import xoc.dta.TestMethod;
import xoc.dta.datalog.IDatalog;
import xoc.dta.datatypes.MultiSiteLong;

public class ReadDeviceCoord extends TestMethod {

    public Long debugLevel=(long) 0;//to control printout and dummy nexus communication

    @Override
    public void execute() {
        ReadDieCoor(debugLevel);
    }
    public void ReadDieCoor(long debuglevel){
        MultiSiteLong wafer_X = context.testProgram().variables().getLong("STDF.X_COORD");
        MultiSiteLong wafer_Y = context.testProgram().variables().getLong("STDF.Y_COORD");
        String datalogACS = "";
        for(int site : wafer_X.getActiveSites()) {
            String acsFormatDieCoor = site+"_"+wafer_X.get(site).toString()+"_"+wafer_Y.get(site).toString();
            if(datalogACS.equals("")) {
                datalogACS = "DIEINFO:"+ acsFormatDieCoor;
            }
            else{
                datalogACS = datalogACS + ";" + acsFormatDieCoor;
            }
        }
        //Debuggin
        //datalogACS="DIEINFO:1_0_4";
        if(debuglevel > 10) {
            println("[AdaptiveTML Debug INFO -> ReadDieCoor]:");
            println("\t[DIE COOR X]:" + wafer_X);
            println("\t[DIE COOR Y]:" + wafer_Y);
        }
        IDatalog datalog = context.datalog();
        //java.sql.Timestamp CurrTime=new java.sql.Timestamp(System.currentTimeMillis());
        //println("Current Time: "+CurrTime.toString());
        //datalog.writeComment("Current Time: "+CurrTime.toString());
        datalog.writeComment(datalogACS);
        //GDRLogs.add(datalogACS);
        return;
    }
}
