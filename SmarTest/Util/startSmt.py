import os
import sys
import subprocess
import time
import shutil
from logging_config import  setup_logging
logger = setup_logging()

def runcmd(cmd):
    try:
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.stdout != b'':
            #logger.info(f'Output: {result.stdout}')
            lines = result.stdout.splitlines()
            for line in lines:
                decoded = line.decode('utf-8')
                logger.info(decoded.strip())
        if result.stderr != b'':
            logger.info(f'Errors: {result.stderr}')
        if result.returncode ==0:
            logger.info(f"run cmd: {cmd} Success")
        else:
            logger.info(f"run cmd: {cmd} Fail")
    except subprocess.CalledProcessError as e:
        logger.info(f'An error occurred: {e.stderr}')
    return result
def CreateWorkSpace(program_path):
    if os.path.exists(program_path+"/workspace"):
        shutil.rmtree(program_path+"/workspace")

    os.makedirs(program_path+"/workspace")
    logger.info(f"workspace: {program_path}/workspace")
    file_path=program_path+"/workspace/projects.map"
    with open(file_path, 'w') as file:
        file.write(f"TestCase_Smt870={program_path}/Case_Smt870")
def cleanEnv():
    #kill Smartest
    logger.info("Kill SmarTest")
    runcmd(["/opt/hp93000/soc/prod_env/lbin/kill_smarTest"])
    #kill tcct
    logger.info("Kill Tcct")
    runcmd(["/opt/hp93000/testcell/bin/killTcct.prod"])
    time.sleep(30)    
    
    
    
if __name__ == "__main__":
    python_file_path = os.path.abspath(__file__)
    program_path = os.path.dirname(python_file_path)   
    root_path = os.path.dirname(program_path)
    execMode:str="eng"
    if len(sys.argv) >=2:
        execMode = sys.argv[1].lower().strip()
    if execMode not in ("eng", "prod"):
        sys.exit("Usage: startSmt.py {eng|prod} {cp|ft}")
    if execMode == "prod" and len(sys.argv) < 3:
        sys.exit("Production requires an explicit test type: startSmt.py prod cp (wafer) or prod ft")
    testType = sys.argv[2].lower().strip() if len(sys.argv) >= 3 else "ft"
    if testType not in ("cp", "ft"):
        sys.exit("Test type must be cp or ft")
    tpName=f"TestCase1_4site_{testType}.prog"
    recipeName=f"acs_tcct_4site_{testType}.xml"
    print (f"run mode: {execMode}; test type: {testType}; recipe: {recipeName}", flush=True)
    CreateWorkSpace(root_path)
    if execMode =="eng":
        count =0
        max_count=6
        finish=False
        cleanEnv()
        ## Start SmarTest offline with target program
        #/opt/hp93000/soc/prod_env/bin/HPSmarTest --data=/home/vincent/workspace_8.7.0 --testprogram=TestCase_Smt870/src/TestCase1/TestCase1_4site_cp.prog -o&
        #cmd = f"/opt/hp93000/soc/prod_env/bin/HPSmarTest --data="+root_path+"/workspace "+"--testprogram=TestCase_Smt870/src/TestCase1/{tpName} -o&"    
        cmd = f"/opt/hp93000/soc/prod_env/bin/HPSmarTest --data={root_path}/workspace --testprogram=TestCase_Smt870/src/TestCase1/{tpName} -o&"   
        runcmd(cmd)
        while count < max_count and finish ==False:
            time.sleep(30)
            exec_result = runcmd(["/opt/acs/nexus/bin/AppDeployer start"])  
            if exec_result.returncode ==0:
                finish=True
            else:
                count+=1  
        
    elif execMode =="prod":
        cleanEnv()
        cmd = f"/opt/hp93000/testcell/bin/tcct -m -r {root_path}/recipe/{recipeName}"
        runcmd(cmd)
    else:
        print(f"{execMode} does not supported")

    
        
     




