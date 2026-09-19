# Gemini / ACS Edge upload

This archive is a source handoff, not a built or deployment-validated container image.
The dashboard is in English. W2 replay data and local notification history are excluded.

## Upload through the Gemini browser

1. Open the Host Controller VM in Gemini.
2. Press Ctrl+Shift+Alt to open the file-transfer panel.
3. Select Devices, then Upload Files, and upload `wafer-watch-gemini-source.zip`.
4. Find the uploaded file in the VM file-transfer location. The actual location depends on the session; it is not necessarily Downloads.
5. In the Host Controller terminal, extract it into your chosen project directory:

```bash
mkdir -p "$HOME/project"
unzip /actual/upload/path/wafer-watch-gemini-source.zip -d "$HOME/project"
cd "$HOME/project/wafer-watch"
```

For ONEAPI development on the Edge VS Code environment, the workshop recommends
`/home/debugger/project` as persistent storage. Uploading to the Host Controller
does not automatically copy files into that Edge development environment.

## Contents

- `realtime/`: JSON backend and English dashboard.
- `artifacts/`: current classifier and supporting statistical model.
- `data/splits/`: 24 replay wafers, filtered manifest and associated metadata; no W2.
- `oneAPI_py3.10/`: supplied ACS SDK sample and native libraries.
- `SmarTest/`: supplied test program, recipes and deployment descriptor.
- `tests/`: local regression tests.
- `doc/`: supplied instructions.
- `deploy/runtime-versions.json`: versions used on the development machine.
- `deploy/package-manifest.json`: SHA-256 hashes of packaged files.

## Current deployment gaps

The trained classifier was produced with Python 3.14.4, scikit-learn 1.8.0,
NumPy 2.4.6, SciPy 1.17.1, joblib 1.5.3 and threadpoolctl 3.6.0.
The supplied native ONEAPI package targets Python 3.10. Do not install these
versions into the official template blindly or assume cross-version joblib
loading is supported. First inspect the template's Python and packages, then
either retrain and verify the model on the supported runtime, or separate the
Python 3.10 ONEAPI adapter from a compatible inference runtime. Changing a
requirements file alone does not convert an existing model.

The SDK sample currently prints measurements and emits a fixed message every
three touchdowns. It is not wired to `ClassifierEngine` or `/api/events`.
The existing Dockerfile copies only the sample `bin/` directory, not the model
or dashboard. Building it as-is builds the official sample only.

The dashboard currently binds to loopback. External browser access needs an
approved proxy/port mapping and corresponding origin configuration. The AUS
descriptor in this package does not establish those routes. Notification storage
at `reports/notifications.sqlite3` needs a persistent writable mount.

## Official sample build / push (not the integrated model)

Run on the Host Controller with access to the AUS registry. Confirm `grp4` is
your assigned namespace. These commands publish the supplied sample only:

```bash
cd "$HOME/project/wafer-watch/oneAPI_py3.10"
sudo docker build -f py-app.dockerfile \
  -t unifiedserver.local/grp4/py-app:sample-v1 .
sudo docker push unifiedserver.local/grp4/py-app:sample-v1
```

For that sample, set `SmarTest/app_descriptor.json` image to
`grp4/py-app:sample-v1`, retaining the container name `py-app`.
Do not use this sample message as model detection evidence.

## Integrated model deployment sequence

1. Validate SDK and model runtime compatibility as described above.
2. Implement the ordered ONEAPI-to-JSON adapter: WaferStart, TestStart,
   measurements, TestEnd and WaferEnd. Preserve tester/head/site identity and
   add PartID and actual decoded pass/fail at TestEnd. Missing required
   measurements must not be filled with normal values.
3. Replace the unconditional three-touchdown sample message with actual
   notification decisions and `ActionManager.set_message(tc.testerId, message)`.
4. Add inference files, models, dependencies and the service entrypoint to the
   image. Configure UI routing and persistent report storage in the supported
   ACS deployment setup.
5. In `SmarTest/Util/startSmt.py`, select `TestCase1_4site_cp.prog` and
   `acs_tcct_4site_cp.xml` for wafer testing. The supplied defaults are FT.
6. Build/push a new version and update the descriptor to that exact version.
7. From `SmarTest`, execute `./runTp.sh prod_run` to launch production simulation.
   This script stops existing SmarTest/TCCT processes before starting the recipe.
8. Verify received events, classification after at least 16 completed dies,
   confidence, notification report and TCCT message delivery.

The outer `SmarTest/recipe` is used by `prod_run`; its request timing is
`On_POSTBIN`, command is `{"key":"prod_action","data":""}` and location is
`edge`. The nested project contains another configuration with different timing
spelling; do not edit the wrong copy. Prediction requests with `key=predict`
belong to the sensor-temperature scenario and are not the trigger for wafer
classification.

Reference: WorkShop_Material.pdf pages 11, 19, 23–26;
Question_20260919.pdf page 6; ONEAPI_Manual.pdf pages 4–8.
