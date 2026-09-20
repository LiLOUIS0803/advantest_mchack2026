# Two independent tasks: Edge analysis, HC dashboards

The upload still contains one top-level `oneAPI_py3.10` directory. It includes
two independently presented tasks and a shared outbound JSON transport:

- **Anomaly detection**: wafer label/confidence, measured Pass/Fail, evidence,
  notification history and acknowledgement. HC page `/anomaly`.
- **Temperature prediction**: requested sensor1–6 predictions, measured values,
  error maps, MAE, raw vs corrected error and die details. HC page `/temperature`.

The temperature page preserves the original Scene 2 template layout, styles and controls.
The anomaly page follows its visual style. There is no combined score, label or anomaly/temperature diagnosis.
Both share one received event stream; a task-specific error disables that task
without disabling the other. Transport corruption, mixed testers or queue overflow
invalidate the shared stream and require restart. One tester per container.

## 1. Upload on HC and prepare the receiver

Upload and extract `oneAPI_py3.10-edge.zip`, then:

```bash
cd /actual/upload/path/oneAPI_py3.10
python3 --version
hostname -I
```

The HC receiver requires Python 3.6+ and only the standard library. Identify the
**HC address reachable from Edge**; do not use the Edge address or localhost below.
Use the actual assigned image namespace in place of grp4 if necessary:

```bash
python3 hc/setup.py --hc-url http://HC_IP:8770 --image grp4/py-app:tasks-v4
python3 hc/start.py --token-file hc-token.txt --data hc-reports.sqlite3
```

The first command creates a random token, `hc-token.txt`, and a private
`app_descriptor.hc.json`. It does not print the token. Keep the token and descriptor
private. The receiver stores JSON and report status in `hc-reports.sqlite3`.
Leave the receiver terminal running (or configure it as a service with the HC administrator).

Open HC Firefox:

```
http://127.0.0.1:8770/
http://127.0.0.1:8770/anomaly
http://127.0.0.1:8770/temperature
```

The pages initially show waiting for Edge. Edge must be allowed to make outbound
TCP connections to HC:8770; no inbound Edge web port or Docker CLI on Edge is needed.
The competition prototype is intended for a controlled network; the ingest endpoint
requires a shared bearer token, but dashboard viewing has no user login.

## 2. Build and push from HC (another terminal)

```bash
cd /actual/upload/path/oneAPI_py3.10
sudo bash tag.sh
```

Default: `unifiedserver.local/grp4/py-app:tasks-v4`.
The Docker build checks Linux Python 3.10, native SDK imports, the portable anomaly
model's 408 reference vectors and all six temperature models. Dependencies are
NumPy 1.26.4 and jsonschema 4.23.0. If the HC cannot access a package index, configure
an approved mirror or Linux Python 3.10 wheels; Windows wheels are not compatible.
Build failure stops the push. Tokens and HC programs are outside `bin/` and are
not included by the Dockerfile's `COPY bin/. ./bin`.

## 3. Configure existing SmarTest and start

Back up the existing SmarTest descriptor. Copy **app_descriptor.hc.json**, not the
unconfigured app_descriptor.json, into the existing HC SmarTest directory as
`app_descriptor.json`. It sets the exact image plus `HC_INGEST_URL` and
`HC_SHARED_TOKEN`. `runTp.sh` copies it to Nexus configuration.

Use the existing `Util/startSmt.py` settings:

```python
tpName="TestCase1_4site_cp.prog"
recipeName="acs_tcct_4site_cp.xml"
```

From that SmarTest directory execute `./runTp.sh prod_run`. This restarts
SmarTest/TCCT. Keep `py-app` as the container name for both the temperature
`predict` calls in Main.flow and the outer recipe's `On_POSTBIN` / `prod_action`.
Do not use the nested recipe's differently spelled `OnPostBin` configuration.

## Event behavior

Anomaly inference updates after TestEnd, with at least 16 completed dies and all
required measurements. Notifications retain the existing >=24 dies and three
consecutive matching non-Normal classifications, or anomalous WaferEnd. Each label
is notified once per wafer run using `set_message`. TCCT collects messages via
`prod_action` / `get_prod`. Final notification delivery still depends on a later
TCCT poll; the HC report is queued regardless of the poll.

Temperature inference responds to `{"key":"predict","data":1}` through 6. The
request enters the ordered event queue so it sees only preceding received data.
`set_wait(...,10,message)` and `get()` run inside the TP request callback as in
the supplied scene2 integration. Requests have a default 0.7 second queue deadline;
confirm timing against the test program's timeout and set_wait units on Gemini.
Expired queued requests are cancelled, late requests use a frozen prediction computed before consuming the first target value,
and are explicitly marked late_request_frozen (not on-time predictions), and repeated requests return the original prediction. No fabricated
average fallback or future-measurement prediction is returned on error.

The supplied Lasso design is retained with median imputation and online bias
correction using previously received residuals. The original full-six-sensor
forecast at sensor1 is not used to overwrite the actual request predictions.
Only predictions made in response to actual requests appear on the temperature
page; unrequested predictions remain blank. Missing-input counts are shown.
The temperature model was refit excluding W2; wafer-group evaluation is in
`bin/artifacts/scene2/evaluation.json`. These are different metrics from anomaly
classification confidence, and the UI keeps them separate.

## Transport and persistence

Edge sends gzip-compressed received-data snapshots in the background (coalesced updates),
with a 60-second network timeout. HC verifies the complete request body before committing,
with separate immutable anomaly report records. Outbound failure is retried from
`REPORT_DIR/hc-outbox.sqlite3`; SDK callbacks never wait for HC networking.
Each process has a run ID, start timestamp and increasing sequence number. HC
rejects duplicate/older sequences and preserves local acknowledgement on retry.
The source selector distinguishes process runs. HC displays stale data after
10 seconds without a snapshot; heartbeat updates are not evidence of new test data.
Accurate ordering of new process runs relies on the Edge clock being correct.

HC persists received JSON/report status. Mount writable persistent storage at
Edge `/var/lib/wafer-watch` through the site's ACS mechanism to retain unsent
reports across container replacement. No mount syntax is invented in the descriptor.
Until such a mount exists, container replacement can lose unsent outbox entries.
Anomaly acknowledgement on HC is a report workflow action, not a tester command.

## First-run field checks

`bin/adapter_config.json` defaults use observed dataset flags 0=pass, 8=fail and
accept measurement flags 0/128. Unknown PartFlag values stop anomaly processing;
extend only after confirming SDK bit semantics. `sdk_value` uses delivered values
without extra scaling. Compare one known measurement with the test program before
switching to `apply_result_scaling`; never scale twice.

Single-value mappings use exact number/suite/text/measurement names. CP/MR aliases
for test 560 are based on the supplied log; other multi-pin names are copied from
SDK pin metadata for temperature. Missing anomaly columns prevent classification.
Retests, duplicate results and overlapping batches require explicit semantics and
are not silently merged. W2 remains excluded from both tasks.

## Verification boundary

Local tests cover task independence, causal prediction, cancelled requests, HC
authentication, restart persistence, stale sequences, retry and acknowledgement.
Python 3.10 syntax and portable model references are checked in packaging/build.
No real HC/Edge/Nexus connection was available locally. Validate actual SDK field
mapping, prediction deadline, TCCT display, HC network reachability and persistence
mounts on Gemini. Neither task automatically stops the tester.

## tasks-v4 field update

Update HC first with git pull, stop the old HC receiver and restart it. Then build and push tasks-v4 using tag.sh; regenerate the descriptor with hc/setup.py --hc-url http://HC_IP:8770 --image grp4/py-app:tasks-v4. Copy the generated descriptor into the active SmarTest directory and restart the test environment. No token rotation is required.

Late temperature requests return only pre-target frozen results. This prevents hindsight inference but does not repair external callback timing. The JSON prediction_timing field distinguishes them; they are excluded from on-time prediction values and MAE in the original temperature UI. Requests with no frozen result still fail. Confirm actual ONEAPI/test-program ordering on site.

## Live view and classification diagnostics (tasks-v4)

Anomaly classification distinguishes insufficient sample count from incomplete measurements/sites and task errors. Data completeness is reported separately from confidence, with per-test missing-die counts. No imputation or retraining is introduced: missing-data tolerance requires separate validation.

The temperature page follows the latest run only. Playback, progress scrubbing and historical source selection are disabled. Live API rejects historical run parameters, packets received more than 10 seconds ago, packets generated more than 15 seconds ago, absent test events or events older than 60 seconds, and completed wafers. It clears the charts while waiting. Edge and HC clocks must be synchronized. Reports remain stored for audit; the model still uses legitimate preceding measurements and its existing online bias strategy.
