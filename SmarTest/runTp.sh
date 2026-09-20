#!/bin/bash
set -eu
action=${1:-}
current_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "$action" in
 load|eng_run) ;;
 prod_run)
    case "${2:-}" in
      cp|ft) ;;
      *) echo "Usage: bash runTp.sh prod_run {cp|ft}; use cp for wafer monitoring" >&2; exit 1 ;;
    esac ;;
 *) echo "Usage: bash runTp.sh {load|eng_run|prod_run}; prod_run requires cp or ft" >&2; exit 1 ;;
esac
cp "${current_path}/app_descriptor.json" /opt/acs/nexus/conf/app_descriptor.json
if [[ "$action" == "load" ]]; then
 command=${current_path}/Util/startSmt.py
 echo "command =${command}"
 python3 ${command}
 
elif [[ "$action" == "eng_run" ]]; then
    if [[ $# -eq 2 ]]; then
        loop=$2
    else
        loop=1
    fi 
    command=${current_path}/Util/tpExec
    echo "command =${command}"
    /opt/hp93000/testcell/bin/run ${command} ${loop}
elif [[ "$action" == "prod_run" ]]; then
    echo "command =${current_path}/Util/startSmt.py prod $2"
    python3 "${current_path}/Util/startSmt.py" prod "$2"
else
   echo "Usage: $0 {load|eng_run|prod_run} [loop_count]"
  exit 1

fi

