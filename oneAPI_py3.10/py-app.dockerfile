FROM unifiedserver.local/all/template-data-app:v22.04
WORKDIR /opt/nexus/OneAPI
COPY bin/. ./bin
ENV ONEAPI_DEBUG 6
WORKDIR /opt/nexus/OneAPI/bin
RUN python3 -c "import sys; assert sys.version_info[:2] == (3,10), sys.version" 
RUN python3 -m pip install --no-cache-dir -r requirements-runtime.txt
RUN python3 verify_runtime.py
ENV REPORT_DIR=/var/lib/wafer-watch
CMD ["python3", "-u", "edge_main.py"]
