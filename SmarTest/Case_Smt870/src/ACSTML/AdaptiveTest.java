package ACSTML;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.sql.Timestamp;
import java.time.format.DateTimeFormatter;
import java.util.Vector;

import libACS.Adaptive.ExecResult;
import libACS.Adaptive.TM;
import libACS.Adaptive.enums.ParamType;
import libACS.Adaptive.ActionInstruction.ActionDef;
import libACS.Adaptive.ActionInstruction.ActionDefs;
import libACS.Adaptive.ActionInstruction.VarAction;
import libACS.Adaptive.ActionInstruction.VarActionCollection;
import libACS.misc.CommonFunc;
import xoc.dta.TestMethod;
import xoc.dta.datalog.IDatalog;


public class AdaptiveTest extends TestMethod {

    public int timeout=1;
    public Integer debugLevel =  0;
    public String AppName="";
    public String AppLoc="edge";
    public String messUtil="";
    private Vector<String> GDRLogs = new Vector<String>();
    private String messUtilPath="";

  @Override
public void initialize()
  {


    super.initialize();
  }

    @Override
    public void setup()
    {
        if(global_variable.LibACSTM.ProgramName().equals("")) {
            global_variable.LibACSTM= new TM(context, debugLevel,AppLoc,AppName,timeout);
        }

        if(!messUtil.equals(""))
        {
            String Proj_Folder=context.testProgram().variables().getString("SYS.PROJECT_DIR").get();
            messUtilPath= Proj_Folder+"/"+messUtil;
        }
        super.setup();
    }
    @Override
    public void execute() {
        //ReadDieCoor(debugLevel);
        Long timerStart = CommonFunc.TimeDiff();
        String Cmd="{\"action\":\"list\"}";
        println("[AdaptiveTest Begin]");
        println("****************************************************************************************");
        RunApaptiveTest(Cmd,AppName, debugLevel,timeout);
        String GDRlog = "Adaptive Test Execution Time:" + CommonFunc.TimeDiff(timerStart).toString()+ " ms";
        GDRLogs.add(GDRlog);
        logGDR(GDRLogs);
        println("****************************************************************************************\n");

    }
    void RunApaptiveTest(String Cmd,String appname ,Integer debugLevel, int timeout)
    {

        ExecResult nExecResult=new ExecResult();
        //String DebugAction="{\"tester\":\"smartest_host\",\"mtesterAction\":[{\"name\":\"default\",\"pool\":[{\"act_typ\": \"tp_var\",\"mactions\":[{\"testsuite\":\"\",\"param\":\"Var1\",\"val\":\"-1=1,1=2,2=3\"}]},{\"act_typ\": \"restore\"}]}]}";
        String DebugAction="";
        GDRLogs.clear();
        VarActionCollection varActionCollection=new VarActionCollection();
        varActionCollection= global_variable.LibACSTM.FetchAction(AppLoc, appname, timeout, Cmd, DebugAction);
        GDRLogs.add("Actions => "+varActionCollection.RecevieData);
        GDRLogs.add("Nexus Process Action Time : "+varActionCollection.processtime.toString()+" ms");
        global_variable.LibACSTM.LogMessage("===   Adaptive Test Start   =====");
        if(varActionCollection.count()>0)
        {
            global_variable.hasAction=true;
            global_variable.ActionStr =  varActionCollection.RecevieData;
            Integer varnum;
            Integer actnum;
            VarAction nVarAction;
            ActionDefs nActions;
            for(varnum=0;varnum<varActionCollection.count();varnum++)
            {
                nVarAction=varActionCollection.var(varnum);
                for(actnum=0;actnum< nVarAction.count();actnum++)
                {
                    nActions=nVarAction.item(actnum);
                    if(nActions.paramType == ParamType.wait)
                    {
                        for(ActionDef nAction: nActions.ActionDefs)
                        {
                            if(!nAction.reason.equals(""))
                            {
                                sendToFifo(nAction.reason);
                            }
                        }
                    }
                }
            }
            if(debugLevel > 0)
            {
                global_variable.LibACSTM.PrintModifySetupPool();
            }
            nExecResult=global_variable.LibACSTM.execACSAdaptive(varActionCollection);
            for(String data:nExecResult.logs)
            {
                GDRLogs.add(data);
            }
            if(debugLevel > 0) {
                global_variable.LibACSTM.PrintModifySetupPool();
            }
        }
        else
        {
            global_variable.hasAction=false;
            global_variable.ActionStr =  "";
        }
    }
    void logGDR(Vector<String> datalogs) {

        if(datalogs.size()>0)
        {
            println("[AdaptiveTML Debug INFO -> logGDR]:");
            println("----------------------------------------------------------");

            IDatalog datalogInterface = context.datalog();
            for(String datalog : datalogs) {
                datalogInterface.add(datalog);
                println("\t[GDR datalog]:" + datalog);

            }
            datalogInterface.writeGenericDataEvent();
            println("----------------------------------------------------------");
        }
        return;
    }
    boolean isProcessRun(String pName)
    {
        try {
            Process process = new ProcessBuilder(
                    "pgrep", "-f", pName)
                    .start();

            return process.waitFor() == 0;
        } catch (Exception e) {
            return false;
        }
    }


    void sendToFifo(String data) {
        String fifoPath = "/tmp/.acs_mess_info";
        String Cmd="";
        Timestamp timestamp = new Timestamp(System.currentTimeMillis());
        String formatted = timestamp.toLocalDateTime().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        try
        {
            if(!messUtilPath.equals(""))
            {
                File util=new File(messUtilPath);
                if(isProcessRun(util.getName())==false)
                {
                    try {
                        new ProcessBuilder("sh", "-c", messUtilPath)
                                .start();
                        System.out.println("Command started");
                    } catch (IOException e) {
                        e.printStackTrace();
                    }
                }


                Cmd ="{\"action\" : \"" + "text" +"\",\"value\": \""+formatted+" "+ data + "\"}";
                println("SendToFifo Write " + data);
                File fifo = new File(fifoPath);
                // Open FIFO and write data
                try (FileOutputStream fos = new FileOutputStream(fifo)) {
                    fos.write(Cmd.getBytes());
                    fos.flush();
                }


            }

        } catch (Exception e) {
            println(e.toString());
        }
    }



}

